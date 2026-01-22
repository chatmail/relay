//! Module for handling outgoing SMTP messages.

use crate::ENCRYPTION_NEEDED_523;
use crate::config::Config;
use crate::message::{check_encrypted, is_securejoin, recipient_matches_passthrough};
pub use crate::smtp_server::Envelope;
use crate::smtp_server::SmtpHandler;
use crate::utils::{extract_address, format_smtp_error};
use async_trait::async_trait;
use governor::{DefaultKeyedRateLimiter, Quota, RateLimiter};
use lettre::{AsyncSmtpTransport, AsyncTransport, Tokio1Executor};
use mailparse::{MailHeaderMap, parse_mail};
use std::sync::{Arc, Mutex};

/// Handler for outgoing SMTP messages.
pub struct OutgoingBeforeQueueHandler {
    config: Arc<Config>,
    send_rate_limiter: Arc<Mutex<DefaultKeyedRateLimiter<String>>>,
}

impl OutgoingBeforeQueueHandler {
    pub fn new(config: Config) -> Self {
        let quota = Quota::per_minute(config.max_user_send_per_minute);
        Self {
            config: Arc::new(config),
            send_rate_limiter: Arc::new(Mutex::new(RateLimiter::keyed(quota))),
        }
    }
}

#[async_trait]
impl SmtpHandler for OutgoingBeforeQueueHandler {
    fn handle_mail(&self, address: &str) -> Result<(), String> {
        log::debug!("handle_MAIL from {address}");

        let parts: Vec<&str> = address.split('@').collect();
        if parts.len() != 2 {
            return Err(format!("500 Invalid from address <{}>", address));
        }

        let Ok(limiter) = self.send_rate_limiter.lock() else {
            log::error!("send_rate_limiter lock panicked!");
            return Err("451 Temporary server error".to_string());
        };
        if let Err(e) = limiter.check_key(&address.to_string()) {
            // "<example@example.org> rate limited until: ..."
            log::debug!("<{address}> {e}");
            return Err(format!("450 4.7.1: Too much mail from <{address}>, {e}"));
        }

        // Cleanup
        //
        // This is only called after a successful check,
        // so a spam of mails from the same user will not cause calling this repeatedly.
        // In the future, in case of higher traffic this can be further optimized by e.g. calling it
        // every N messages or in a separate task every N minutes.
        // Time complexity is O(n) where n is the number of unique senders in the last minute.
        limiter.retain_recent();

        Ok(())
    }

    fn check_data(&self, envelope: &Envelope) -> Result<(), String> {
        log::debug!("Processing DATA message from {}", envelope.mail_from);

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
        if envelope.rcpt_to.len() == 1
            && let Some(rcpt_to) = envelope.rcpt_to.first()
            && *rcpt_to == envelope.mail_from
        {
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
                log::warn!("Rejected unencrypted mail from: {}", envelope.mail_from);
                return Err(ENCRYPTION_NEEDED_523.to_string());
            }
        }

        Ok(())
    }

    async fn reinject_mail(&self, envelope: &Envelope) -> Result<(), String> {
        log::debug!("Re-injecting the mail that passed checks");

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
