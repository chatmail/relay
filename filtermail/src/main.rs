mod config;
pub(crate) mod error;
pub(crate) mod inbound;
pub(crate) mod message;
pub(crate) mod openpgp;
pub(crate) mod outbound;
pub(crate) mod rate_limiter;
pub(crate) mod smtp_server;
pub(crate) mod utils;

use config::Config;
use env_logger::Env;
use inbound::IncomingBeforeQueueHandler;
use outbound::OutgoingBeforeQueueHandler;
use smtp_server::run_smtp_server;
use std::env;
use std::process;
use std::sync::Arc;

const ENCRYPTION_NEEDED_523: &str = "523 Encryption Needed: Invalid Unencrypted Mail";

#[tokio::main]
async fn main() {
    // default to info level
    let env = Env::new().filter_or("RUST_LOG", "info");
    env_logger::Builder::from_env(env)
        // disable timestamps - automatically added by systemd
        .format_timestamp(None)
        .init();

    let args: Vec<String> = env::args().collect();
    if args.len() != 3 {
        eprintln!("Usage: {} <config_file> <mode>", args[0]);
        eprintln!("  mode: incoming or outgoing");
        process::exit(1);
    }

    let config_path = &args[1];
    let mode = &args[2];

    if mode != "incoming" && mode != "outgoing" {
        eprintln!("Error: mode must be 'incoming' or 'outgoing'");
        process::exit(1);
    }

    let config = match Config::from_file(config_path) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Failed to read config: {}", e);
            process::exit(1);
        }
    };

    if mode == "outgoing" {
        let handler = Arc::new(OutgoingBeforeQueueHandler::new(config.clone()));
        let addr = format!("127.0.0.1:{}", config.filtermail_smtp_port);
        let max_size = config.max_message_size;
        log::debug!("Outgoing SMTP server listening on {}", addr);

        if let Err(e) = run_smtp_server(&addr, handler, max_size).await {
            eprintln!("Server error: {}", e);
            process::exit(1);
        }
    } else {
        let handler = Arc::new(IncomingBeforeQueueHandler::new(config.clone()));
        let addr = format!("127.0.0.1:{}", config.filtermail_smtp_port_incoming);
        let max_size = config.max_message_size;
        log::debug!("Incoming SMTP server listening on {}", addr);

        if let Err(e) = run_smtp_server(&addr, handler, max_size).await {
            eprintln!("Server error: {}", e);
            process::exit(1);
        }
    }
}
