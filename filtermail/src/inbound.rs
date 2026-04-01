//! Module for handling incoming SMTP messages.

use crate::ENCRYPTION_NEEDED_523;
use crate::config::Config;
use crate::dkim_verifier::DkimVerifier;
use crate::message::{check_encrypted, is_securejoin};
pub use crate::smtp_server::Envelope;
use crate::smtp_server::SmtpHandler;
use crate::utils::{AddressDomain, extract_address, log_eml};
use async_trait::async_trait;
use mailparse::{MailHeaderMap, parse_mail};
use std::net::SocketAddr;
use std::str::FromStr;

/// Handler for incoming SMTP messages.
pub struct IncomingBeforeQueueHandler {
    config: Config,
    dkim_verifier: DkimVerifier,
    skip_dkim: bool,
    reinject_addr: SocketAddr,
}

impl IncomingBeforeQueueHandler {
    pub fn new(config: Config, skip_dkim: bool) -> Result<Self, crate::error::Error> {
        let reinject_addr =
            crate::resolve_addr(&config.postfix_host, config.postfix_reinject_port_incoming)?;
        Ok(Self {
            config,
            dkim_verifier: DkimVerifier::new()?,
            skip_dkim,
            reinject_addr,
        })
    }

    /// Verify the origin of the email by performing a DKIM verification on a regular domain.
    ///
    /// Currently a no-op for valid domain-literals.
    async fn verify_origin(&self, envelope: &Envelope, from_addr: &str) -> Result<(), String> {
        let from_domain = AddressDomain::from_str(from_addr).map_err(|e| e.smtp_response())?;

        match from_domain {
            AddressDomain::Literal(_) => {
                // Subject to change: we currently don't perform any additional authentication
                // for domain-literals and rely purely on encryption.
            }
            AddressDomain::Name(domain) => {
                if !self.skip_dkim
                    && let Err(e) = self.dkim_verifier.verify(&envelope.data, &domain).await
                {
                    let eml_path = log_eml("dkim-verify", &envelope.data)
                        .await
                        .map(|path| path.to_string_lossy().to_string())
                        .unwrap_or_else(|e| {
                            log::error!("Failed to save rejected message to file: {e}");
                            "ERR".to_string()
                        });
                    log::info!("Rejected message stored at: {eml_path}");
                    return Err(e);
                }
            }
        }

        Ok(())
    }
}

#[async_trait]
impl SmtpHandler for IncomingBeforeQueueHandler {
    fn handle_mail(&self, _address: &str) -> Result<(), String> {
        Ok(())
    }

    async fn check_data(&self, envelope: &mut Envelope) -> Result<(), String> {
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

        log::debug!("Processing DATA message from {from_addr}");

        if !envelope.mail_from.eq_ignore_ascii_case(&from_addr) {
            // If the MAIL FROM doesn't match the From header, we do not reject the mail,
            // as this can be caused by e.g. SRS forwarding.
            // Instead, we reset the envelope address, so it is reinjected as
            // `MAIL FROM:<>` to prevent sending a bounce message.
            // <https://github.com/chatmail/filtermail/issues/67>
            envelope.mail_from = String::new();
        }

        envelope.rcpt_to = envelope
            .rcpt_to
            .iter()
            .filter(|s| !self.config.is_disabled(s))
            .cloned()
            .collect();

        let mail_encrypted = check_encrypted(&message, false);
        log::debug!("mail_encrypted: {mail_encrypted}");
        log::debug!("is_securejoin: {}", is_securejoin(&message));

        // Allow encrypted or securejoin messages
        if mail_encrypted || is_securejoin(&message) {
            log::info!("Incoming: Filtering encrypted mail.");
            return self.verify_origin(envelope, &from_addr).await;
        }

        log::info!("Incoming: Filtering unencrypted mail.");

        // Allow cleartext mailer-daemon messages
        if let Some(auto_submitted) = message.headers.get_first_value("Auto-Submitted")
            && !auto_submitted.is_empty()
            && from_addr.to_lowercase().starts_with("mailer-daemon@")
            && message.ctype.mimetype == "multipart/report"
        {
            return self.verify_origin(envelope, &from_addr).await;
        }

        for recipient in &envelope.rcpt_to {
            if !self.config.is_cleartext_ok(recipient) {
                log::warn!("Rejected unencrypted mail from: {from_addr}");
                return Err(ENCRYPTION_NEEDED_523.to_string());
            }
        }

        self.verify_origin(envelope, &from_addr).await
    }

    async fn reinject_mail(&self, envelope: &Envelope) -> Result<(), String> {
        log::debug!("Re-injecting the mail that passed checks");

        crate::smtp_client::send(self.reinject_addr, envelope)
            .await
            .map_err(|e| {
                log::warn!("Failed to re-inject mail: {}", e);
                e.smtp_response()
            })?;

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rstest::{fixture, rstest};
    use testresult::TestResult;

    #[fixture]
    fn config() -> Config {
        Config::default()
    }

    /// Test that domain-literals are not rejected by origin check.
    #[rstest]
    #[tokio::test]
    #[case::ipv4(include_bytes!("../test_data/encrypted-ipv4.eml"), "one@[192.0.2.0]")]
    #[case::ipv6(include_bytes!("../test_data/encrypted-ipv6.eml"), "one@[IPv6:2001:db8::1]")]
    async fn test_domain_literals_allowed(
        #[case] eml: &[u8],
        #[case] address: &str,
        config: Config,
    ) -> TestResult {
        let handler = IncomingBeforeQueueHandler::new(config, false)?;
        let mut envelope = Envelope {
            mail_from: address.to_string(),
            origin_ip: "".to_string(), // Currently shouldn't be relevant.
            data: eml.to_vec(),
            rcpt_to: vec!["does.not.matter@example.org".to_string()],
        };
        Ok(handler.check_data(&mut envelope).await?)
    }
}
