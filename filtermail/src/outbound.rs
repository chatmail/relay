//! Module for handling outgoing SMTP messages.

use crate::ENCRYPTION_NEEDED_523;
use crate::config::Config;
use crate::message::{check_encrypted, is_securejoin, recipient_matches_passthrough};
use crate::rate_limiter::SendRateLimiter;
pub use crate::smtp_server::Envelope;
use crate::smtp_server::SmtpHandler;
use crate::utils::{extract_address, format_smtp_error};
use async_trait::async_trait;
use lettre::{AsyncSmtpTransport, AsyncTransport, Tokio1Executor};
use mailparse::{MailHeaderMap, parse_mail};
use std::sync::{Arc, Mutex};

/// Handler for outgoing SMTP messages.
pub struct OutgoingBeforeQueueHandler {
    config: Arc<Config>,
    send_rate_limiter: Arc<Mutex<SendRateLimiter>>,
}

impl OutgoingBeforeQueueHandler {
    pub fn new(config: Config) -> Self {
        Self {
            config: Arc::new(config),
            send_rate_limiter: Arc::new(Mutex::new(SendRateLimiter::default())),
        }
    }
}

#[async_trait]
impl SmtpHandler for OutgoingBeforeQueueHandler {
    fn handle_mail(&self, address: &str) -> Result<(), String> {
        log::info!("handle_MAIL from {}", address);

        let parts: Vec<&str> = address.split('@').collect();
        if parts.len() != 2 {
            return Err(format!("500 Invalid from address <{}>", address));
        }

        let max_sent = self.config.max_user_send_per_minute;
        let mut limiter = self.send_rate_limiter.lock().unwrap();
        if !limiter.is_sending_allowed(address, max_sent) {
            log::debug!("Rate limit exceeded for {}", address);
            return Err(format!("450 4.7.1: Too much mail from {}", address));
        }

        Ok(())
    }

    fn check_data(&self, envelope: &Envelope) -> Result<(), String> {
        log::info!("Processing DATA message from {}", envelope.mail_from);

        let message = match parse_mail(&envelope.data) {
            Ok(m) => m,
            Err(e) => return Err(format!("500 Failed to parse message: {}", e)),
        };

        let mail_encrypted = check_encrypted(&message, true);

        let from_header = message
            .headers
            .get_first_value("From")
            .unwrap_or_default()
            .trim()
            .to_string();

        let from_addr = extract_address(&from_header)
            .ok_or(format!("500 Invalid FROM header: {from_header}"))?;

        if !envelope.mail_from.eq_ignore_ascii_case(&from_addr) {
            return Err(format!(
                "500 Invalid FROM <{}> for <{}>",
                from_addr, envelope.mail_from
            ));
        }

        // Allow encrypted or securejoin messages
        if mail_encrypted || is_securejoin(&message) {
            log::info!("Outgoing: Filtering encrypted mail.");
            return Ok(());
        }

        log::info!("Outgoing: Filtering unencrypted mail.");

        // Allow passthrough senders
        if self
            .config
            .passthrough_senders
            .contains(&envelope.mail_from)
        {
            return Ok(());
        }

        // Allow self-sent Autocrypt Setup Message
        if envelope.rcpt_to.len() == 1 && envelope.rcpt_to[0] == envelope.mail_from {
            let subject = message
                .headers
                .get_first_value("Subject")
                .unwrap_or_default();
            if subject == "Autocrypt Setup Message" && message.ctype.mimetype == "multipart/mixed" {
                return Ok(());
            }
        }

        for recipient in &envelope.rcpt_to {
            if !recipient_matches_passthrough(recipient, &self.config.passthrough_recipients) {
                log::info!("Rejected unencrypted mail.");
                return Err(ENCRYPTION_NEEDED_523.to_string());
            }
        }

        Ok(())
    }

    async fn reinject_mail(&self, envelope: &Envelope) -> Result<(), String> {
        log::info!("Re-injecting the mail that passed checks");

        let mailer = AsyncSmtpTransport::<Tokio1Executor>::builder_dangerous("localhost")
            .port(self.config.postfix_reinject_port)
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
