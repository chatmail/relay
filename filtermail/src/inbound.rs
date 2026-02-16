//! Module for handling incoming SMTP messages.

use crate::ENCRYPTION_NEEDED_523;
use crate::config::Config;
use crate::dkim_verifier::DkimVerifier;
use crate::message::{check_encrypted, is_securejoin};
pub use crate::smtp_server::Envelope;
use crate::smtp_server::SmtpHandler;
use crate::utils::{AddressDomain, extract_address};
use async_trait::async_trait;
use mailparse::{MailHeaderMap, parse_mail};
use std::str::FromStr;

/// Handler for incoming SMTP messages.
pub struct IncomingBeforeQueueHandler {
    config: Config,
    dkim_verifier: DkimVerifier,
}

impl IncomingBeforeQueueHandler {
    pub fn new(config: Config) -> Result<Self, crate::error::Error> {
        Ok(Self {
            config,
            dkim_verifier: DkimVerifier::new()?,
        })
    }
}

#[async_trait]
impl SmtpHandler for IncomingBeforeQueueHandler {
    fn handle_mail(&self, _address: &str) -> Result<(), String> {
        Ok(())
    }

    async fn check_data(&self, envelope: &Envelope) -> Result<(), String> {
        log::debug!("Processing DATA message from {}", envelope.mail_from);

        let message = match parse_mail(&envelope.data) {
            Ok(m) => m,
            Err(e) => return Err(format!("500 Failed to parse message: {}", e)),
        };

        let from_header = message
            .headers
            .get_first_value("From")
            .unwrap_or_default()
            .trim()
            .to_string();

        let Some(from_addr) = extract_address(&from_header) else {
            return Err(format!("500 Invalid FROM header: {from_header}"));
        };

        let from_domain = AddressDomain::from_str(&from_addr).map_err(|e| e.smtp_response())?;

        match from_domain {
            AddressDomain::Literal(ip) => {
                if !envelope.origin_ip.eq_ignore_ascii_case(&ip) {
                    log::warn!(
                        "Received invalid origin address: {ip}, actual: {}",
                        envelope.origin_ip
                    );
                    return Err(format!(
                        "500 Invalid FROM domain literal: {ip} does not match origin IP {}",
                        envelope.origin_ip
                    ));
                }
            }
            AddressDomain::Name(domain) => {
                self.dkim_verifier.verify(&envelope.data, &domain).await?;
            }
        }

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
            && from_addr.to_lowercase().starts_with("mailer-daemon@")
            && message.ctype.mimetype == "multipart/report"
        {
            return Ok(());
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

        crate::smtp_client::send(self.config.postfix_reinject_port_incoming, envelope)
            .await
            .map_err(|e| {
                log::warn!("Failed to re-inject mail: {}", e);
                e.smtp_response()
            })?;

        Ok(())
    }
}
