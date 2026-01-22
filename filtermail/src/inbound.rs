//! Module for handling incoming SMTP messages.

use crate::ENCRYPTION_NEEDED_523;
use crate::config::Config;
use crate::message::{check_encrypted, is_securejoin};
use crate::smtp_server::SmtpHandler;
use async_trait::async_trait;
use lettre::{AsyncSmtpTransport, AsyncTransport, Tokio1Executor};
use mailparse::{MailHeaderMap, parse_mail};
use std::sync::Arc;

pub use crate::smtp_server::Envelope;
use crate::utils::{extract_address, format_smtp_error};

/// Handler for incoming SMTP messages.
pub struct IncomingBeforeQueueHandler {
    config: Arc<Config>,
}

impl IncomingBeforeQueueHandler {
    pub fn new(config: Config) -> Self {
        Self {
            config: Arc::new(config),
        }
    }
}

#[async_trait]
impl SmtpHandler for IncomingBeforeQueueHandler {
    fn handle_mail(&self, _address: &str) -> Result<(), String> {
        Ok(())
    }

    fn check_data(&self, envelope: &Envelope) -> Result<(), String> {
        log::debug!("Processing DATA message from {}", envelope.mail_from);

        let message = match parse_mail(&envelope.data) {
            Ok(m) => m,
            Err(e) => return Err(format!("500 Failed to parse message: {}", e)),
        };

        let mail_encrypted = check_encrypted(&message, false);
        log::debug!("mail_encrypted: {mail_encrypted}");
        log::debug!("is_securejoin: {}", is_securejoin(&message));

        // Allow encrypted or securejoin messages
        if mail_encrypted || is_securejoin(&message) {
            log::info!("Incoming: Filtering encrypted mail.");
            return Ok(());
        }

        log::info!("Incoming: Filtering unencrypted mail.");

        // Allow cleartext mailer-daemon messages
        if let Some(auto_submitted) = message.headers.get_first_value("Auto-Submitted")
            && !auto_submitted.is_empty()
        {
            let from_header = message
                .headers
                .get_first_value("From")
                .unwrap_or_default()
                .trim()
                .to_string();

            if let Some(from_addr) = extract_address(&from_header)
                && from_addr.to_lowercase().starts_with("mailer-daemon@")
                && message.ctype.mimetype == "multipart/report"
            {
                return Ok(());
            }
        }

        for recipient in &envelope.rcpt_to {
            if !self.config.is_cleartext_ok(recipient) {
                log::warn!("Rejected unencrypted mail from: {}", envelope.mail_from);
                return Err(ENCRYPTION_NEEDED_523.to_string());
            }
        }

        Ok(())
    }

    async fn reinject_mail(&self, envelope: &Envelope) -> Result<(), String> {
        log::debug!("Re-injecting the mail that passed checks");

        let mailer = AsyncSmtpTransport::<Tokio1Executor>::builder_dangerous("localhost")
            .port(self.config.postfix_reinject_port_incoming)
            .build();

        let envelope_data = lettre::address::Envelope::new(
            Some(
                envelope
                    .mail_from
                    .parse()
                    .map_err(|e| format!("Invalid from address: {}", e))?,
            ),
            envelope
                .rcpt_to
                .iter()
                .map(|addr| addr.parse())
                .collect::<Result<Vec<_>, _>>()
                .map_err(|e| format!("Invalid to address: {}", e))?,
        )
        .map_err(|e| format!("Failed to create envelope: {}", e))?;

        mailer
            .send_raw(&envelope_data, &envelope.data)
            .await
            .map_err(format_smtp_error)?;

        Ok(())
    }
}
