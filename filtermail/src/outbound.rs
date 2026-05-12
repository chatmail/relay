//! Module for handling outgoing SMTP messages.

use crate::config::Config;
use crate::message::{check_encrypted, is_securejoin};
use crate::smtp_client::SmtpConnectionPool;
use crate::smtp_responses::ENCRYPTION_NEEDED_523;
use crate::smtp_responses::OK_250;
use crate::smtp_server::{SmtpHandler, Transaction};
use crate::utils::{build_resolver, extract_address};
use async_trait::async_trait;
use governor::clock::MonotonicClock;
use governor::middleware::NoOpMiddleware;
use governor::{Quota, RateLimiter};
use hickory_resolver::TokioResolver;
use mailparse::{MailHeaderMap, parse_mail};
use std::sync::Arc;

/// Handler for outgoing SMTP messages.
pub struct OutgoingBeforeQueueHandler {
    config: Config,
    dns_resolver: Arc<TokioResolver>,

    // We explicitly use standard MonotonicClock here.
    // governor 0.10.4 by default uses "quanta" clock
    // if the feature "quanta" is enabled
    // and it has a known problem
    // of sometimes jumping back in time
    // when moved between CPU cores:
    // <https://github.com/metrics-rs/quanta/issues/111>
    send_rate_limiter: RateLimiter<
        String,
        governor::state::keyed::DashMapStateStore<String>,
        MonotonicClock,
        NoOpMiddleware<std::time::Instant>,
    >,
    smtp_connection_pool: Arc<SmtpConnectionPool>,
}

impl OutgoingBeforeQueueHandler {
    pub fn new(config: Config) -> Result<Self, crate::error::Error> {
        let quota = Quota::per_minute(config.max_user_send_per_minute)
            .allow_burst(config.max_user_send_burst_size);
        let dns_resolver = Arc::new(build_resolver()?);
        let send_rate_limiter = RateLimiter::dashmap_with_clock(quota, MonotonicClock);
        Ok(Self {
            config,
            dns_resolver,
            send_rate_limiter,
            smtp_connection_pool: SmtpConnectionPool::new(),
        })
    }
}

#[async_trait]
impl SmtpHandler for OutgoingBeforeQueueHandler {
    type State = ();

    fn handle_mail_from(&self, address: &str) -> Result<(), String> {
        log::debug!("handle_MAIL from {address}");

        let parts: Vec<&str> = address.split('@').collect();
        if parts.len() != 2 {
            return Err(format!("500 Invalid from address <{}>", address));
        }

        if let Err(e) = self.send_rate_limiter.check_key(&address.to_string()) {
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
        self.send_rate_limiter.retain_recent();

        Ok(())
    }

    async fn check_data(&self, transaction: &mut Transaction<Self::State>) -> Result<(), String> {
        let message = match parse_mail(&transaction.envelope.data) {
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

        transaction.envelope.rcpt_to = transaction
            .envelope
            .rcpt_to
            .iter()
            .filter(|s| {
                let disabled = self.config.is_disabled(s);
                if disabled {
                    log::warn!("Disabled recipient: {s}; removing from RCPT TO");
                }
                !disabled
            })
            .cloned()
            .collect();

        // MAIL FROM is our source of truth for outbound messages,
        // as this address is checked by postfix against the username before sending it
        // to filtermail.
        log::debug!(
            "Processing DATA message from {}",
            transaction.envelope.mail_from
        );

        if !transaction
            .envelope
            .mail_from
            .eq_ignore_ascii_case(&from_addr)
        {
            return Err(format!(
                "500 Invalid FROM <{}> for <{}>",
                from_addr, transaction.envelope.mail_from
            ));
        }

        // Allow encrypted or securejoin messages
        if mail_encrypted || is_securejoin(&message) {
            log::info!("Outgoing: Filtering encrypted mail.");
            return Ok(());
        }

        log::info!("Outgoing: Filtering unencrypted mail.");

        // Allow self-sent Autocrypt Setup Message
        if transaction.envelope.rcpt_to.len() == 1
            && let Some(rcpt_to) = transaction.envelope.rcpt_to.first()
            && *rcpt_to == from_addr
        {
            let subject = message
                .headers
                .get_first_value("Subject")
                .unwrap_or_default();
            if subject == "Autocrypt Setup Message" && message.ctype.mimetype == "multipart/mixed" {
                return Ok(());
            }
        }

        log::warn!("Rejected unencrypted mail from: {from_addr}");
        Err(ENCRYPTION_NEEDED_523.to_string())
    }

    async fn reinject_mail(&self, transaction: &Transaction<Self::State>) -> Result<(), String> {
        log::debug!("Re-injecting the mail that passed checks");
        let hostname = format!("[{}]", self.config.filtermail_host);
        crate::smtp_client::send(
            &self.config.postfix_host,
            self.config.postfix_reinject_port,
            &transaction.envelope,
            &hostname,
            None,
            self.dns_resolver.clone(),
            self.smtp_connection_pool.clone(),
        )
        .await
        .map_err(|e| {
            log::warn!("Failed to re-inject mail: {}", e);
            e.smtp_response()
        })?;

        Ok(())
    }

    async fn handle_data_dot(
        &self,
        transaction: &mut Transaction<Self::State>,
    ) -> Result<String, String> {
        log::debug!("handle_DATA before-queue");
        self.check_data(transaction).await?;
        if self.config.is_disabled(&transaction.envelope.mail_from) {
            log::warn!(
                "Dropping mail; Sender {} is disabled.",
                transaction.envelope.mail_from
            );
            return Ok(OK_250.to_string());
        }
        if transaction.envelope.rcpt_to.is_empty() {
            log::warn!("Dropping mail; All recipients disabled.");
            return Ok(OK_250.to_string());
        }
        self.reinject_mail(transaction).await.map_err(|e| {
            log::warn!("Failed to reinject mail: {e}");
            e
        })?;
        Ok(OK_250.to_string())
    }
}
