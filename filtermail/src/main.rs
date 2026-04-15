#![doc = include_str!("../README.md")]
#![forbid(unsafe_code)]
#![warn(
    unused,
    clippy::correctness,
    missing_debug_implementations,
    missing_docs,
    clippy::all,
    clippy::wildcard_imports,
    clippy::needless_borrow,
    clippy::cast_lossless,
    clippy::unused_async,
    clippy::explicit_iter_loop,
    clippy::explicit_into_iter_loop,
    clippy::cloned_instead_of_copied
)]
#![cfg_attr(not(test), forbid(clippy::indexing_slicing))]
#![cfg_attr(not(test), forbid(clippy::string_slice))]
#![allow(
    clippy::match_bool,
    clippy::mixed_read_write_in_expression,
    clippy::bool_assert_comparison,
    clippy::manual_split_once,
    clippy::format_push_string,
    clippy::bool_to_int_with_if
)]
mod config;
mod dkim_verifier;
pub(crate) mod error;
pub(crate) mod inbound;
pub(crate) mod message;
pub(crate) mod openpgp;
pub(crate) mod outbound;
pub(crate) mod smtp_client;
pub(crate) mod smtp_server;
mod tls;
mod transport;
pub(crate) mod utils;

use crate::transport::TransportHandler;
use config::Config;
use env_logger::Env;
use inbound::IncomingBeforeQueueHandler;
use outbound::OutgoingBeforeQueueHandler;
use smtp_server::run_smtp_server;
use std::env;
use std::process;
use std::str::FromStr;
use std::sync::Arc;

const ENCRYPTION_NEEDED_523: &str = "523 Encryption Needed: Invalid Unencrypted Mail";

#[derive(Debug, Copy, Clone, PartialEq, Eq)]
enum Mode {
    Outgoing,
    Incoming,
    Transport,
}

impl FromStr for Mode {
    type Err = &'static str;

    fn from_str(mode: &str) -> Result<Self, Self::Err> {
        match mode {
            "outgoing" => Ok(Mode::Outgoing),
            "incoming" => Ok(Mode::Incoming),
            "transport" => Ok(Mode::Transport),
            _ => Err("Error: mode must be 'incoming', 'outgoing' or 'transport'"),
        }
    }
}

#[tokio::main]
async fn main() -> Result<(), error::Error> {
    // default to info level
    let env = Env::new().filter_or("RUST_LOG", "info");
    env_logger::Builder::from_env(env)
        // disable timestamps - automatically added by systemd
        .format_timestamp(None)
        .init();

    tokio_rustls::rustls::crypto::ring::default_provider()
        .install_default()
        .expect("Failed to set up rustls crypto provider.");

    let args: Vec<String> = env::args().collect();
    if args.len() != 3 {
        eprintln!(
            "Usage: {} <config_file> <mode>",
            args.first().unwrap_or(&"filtermail".to_string())
        );
        eprintln!("  mode: incoming, outgoing or transport");
        process::exit(1);
    }

    let Some(config_path) = args.get(1) else {
        unreachable!("args length checked above")
    };
    let Some(mode) = args.get(2) else {
        unreachable!("args length checked above")
    };

    let mode = match Mode::from_str(mode) {
        Ok(mode) => mode,
        Err(e) => {
            eprintln!("{e}");
            process::exit(1);
        }
    };

    let config = match Config::from_file(config_path) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Failed to read config: {}", e);
            process::exit(1);
        }
    };

    match mode {
        Mode::Outgoing => {
            let addr = (config.filtermail_host, config.filtermail_smtp_port);
            let handler = Arc::new(OutgoingBeforeQueueHandler::new(config.clone())?);
            let max_size = config.max_message_size;
            log::debug!("Outgoing SMTP server listening on {}:{}", addr.0, addr.1);

            if let Err(e) = run_smtp_server(&addr, handler, max_size).await {
                eprintln!("Server error: {}", e);
                process::exit(1);
            }
        }
        Mode::Incoming => {
            // Skip DKIM verification (used for tests).
            let skip_dkim = env::var("FILTERMAIL_SKIP_DKIM")
                .map(|val| val == "1" || val.eq_ignore_ascii_case("true"))
                .unwrap_or(false);

            if skip_dkim {
                log::warn!("DKIM verification DISABLED! This should not be used in production.");
            }

            let handler = Arc::new(IncomingBeforeQueueHandler::new(config.clone(), skip_dkim)?);
            let max_size = config.max_message_size;

            let mut server_set = tokio::task::JoinSet::new();

            let addr_smtp = (config.filtermail_host, config.filtermail_smtp_port_incoming);
            let handler_smtp = handler.clone();
            server_set
                .spawn(async move { run_smtp_server(&addr_smtp, handler_smtp, max_size).await });
            log::debug!(
                "Incoming SMTP server listening on {}:{}",
                addr_smtp.0,
                addr_smtp.1
            );

            while let Some(result) = server_set.join_next().await {
                if let Err(e) = result {
                    eprintln!("Server error: {}", e);
                    process::exit(1);
                }
            }
        }
        Mode::Transport => {
            let addr = (
                config.filtermail_host,
                config.filtermail_lmtp_port_transport,
            );
            let handler = Arc::new(TransportHandler::new(config.clone())?);
            let max_size = config.max_message_size;
            log::debug!("Transport SMTP server listening on {}:{}", addr.0, addr.1);

            if let Err(e) = run_smtp_server(&addr, handler, max_size).await {
                eprintln!("Server error: {}", e);
                process::exit(1);
            }
        }
    };

    Ok(())
}
