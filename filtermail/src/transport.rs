use crate::config::Config;
use crate::smtp_client::{SmtpConnectionPool, TlsConfig};
use crate::smtp_server::{Envelope, SmtpHandler};
use crate::tls;
use crate::utils::{AddressDomain, build_resolver};
use async_trait::async_trait;
use hickory_resolver::{TokioResolver, proto::rr::RData};
use http_body_util::BodyExt;
use hyper::body::Bytes;
use hyper_rustls::HttpsConnector;
use hyper_util::client::legacy::connect::HttpConnector;
use std::collections::BTreeMap;
use std::str::FromStr;
use std::sync::Arc;
use std::time::Duration;
use tokio::task::{JoinHandle, JoinSet};
use tokio_rustls::rustls;

pub const HEADER_MAIL_FROM: &str = "X-MAIL-FROM";
pub const HEADER_RCPT_TO: &str = "X-MAIL-TO";

/// Cheaply clonable HTTPS client.
///
/// Holds regular secure variant and relaxed - without certificate verification.
///
/// Connection pool handled internally by [`hyper_util::client::legacy::Client`].
#[derive(Clone)]
struct HttpsClient {
    pub secure: hyper_util::client::legacy::Client<
        HttpsConnector<HttpConnector>,
        http_body_util::Full<Bytes>,
    >,
    pub relaxed: hyper_util::client::legacy::Client<
        HttpsConnector<HttpConnector>,
        http_body_util::Full<Bytes>,
    >,
}

impl HttpsClient {
    /// Creates a new `[HttpsClient]`.
    pub fn new(tls_resumption_store: Arc<rustls::client::ClientSessionMemoryCache>) -> Self {
        let tls_client_config = tls::configure_rustls(tls_resumption_store.clone(), false);
        let https_connector = hyper_rustls::HttpsConnectorBuilder::new()
            .with_tls_config(tls_client_config)
            .https_only()
            .enable_http1()
            .enable_http2()
            .build();
        let https_client =
            hyper_util::client::legacy::Client::builder(hyper_util::rt::TokioExecutor::new())
                .build(https_connector);

        let tls_client_config_relaxed = tls::configure_rustls(tls_resumption_store, true);
        let https_connector_relaxed = hyper_rustls::HttpsConnectorBuilder::new()
            .with_tls_config(tls_client_config_relaxed)
            .https_only()
            .enable_http1()
            .enable_http2()
            .build();
        let https_client_relaxed =
            hyper_util::client::legacy::Client::builder(hyper_util::rt::TokioExecutor::new())
                .build(https_connector_relaxed);

        Self {
            secure: https_client,
            relaxed: https_client_relaxed,
        }
    }
}

pub struct TransportHandler {
    config: Config,
    dns_resolver: Arc<TokioResolver>,
    tls_resumption_store: Arc<rustls::client::ClientSessionMemoryCache>,
    smtp_connection_pool: Arc<SmtpConnectionPool>,
    https_client: HttpsClient,
    mxdeliv_unsupported_hosts: Arc<retainer::Cache<String, bool>>,
    monitor_handle: JoinHandle<()>,
}

impl TransportHandler {
    pub fn new(config: Config) -> Result<Self, crate::error::Error> {
        let dns_resolver = Arc::new(build_resolver()?);
        let tls_resumption_store = Arc::new(rustls::client::ClientSessionMemoryCache::new(256));
        let https_client = HttpsClient::new(tls_resumption_store.clone());

        let mxdeliv_cache = Arc::new(retainer::Cache::new());
        let mxdeliv_cache_clone = mxdeliv_cache.clone();

        let monitor_handle = tokio::spawn(async move {
            mxdeliv_cache_clone
                .monitor(4, 0.25, Duration::from_secs(10))
                .await
        });

        Ok(Self {
            config,
            dns_resolver,
            tls_resumption_store,
            smtp_connection_pool: SmtpConnectionPool::new(),
            https_client,
            mxdeliv_unsupported_hosts: mxdeliv_cache,
            monitor_handle,
        })
    }

    /// Handles a single email transaction for a single recipient domain.
    #[expect(clippy::too_many_arguments)]
    async fn handle_single_domain(
        tls_resumption_store: Arc<rustls::client::ClientSessionMemoryCache>,
        smtp_connection_pool: Arc<SmtpConnectionPool>,
        mxdeliv_unsupported_hosts: Arc<retainer::Cache<String, bool>>,
        https_client: HttpsClient,
        dns_resolver: Arc<TokioResolver>,
        domain: AddressDomain,
        envelope: Envelope,
        client_hostname: String,
    ) -> Result<String, String> {
        let mut allow_invalid_cert = false;
        let mut skip_tls = false; // only respected by smtp channel

        let mx_hosts = match domain {
            // no-DNS setup; assume the ip from email address is the destination.
            AddressDomain::Literal(ip) => {
                // We allow self-signed certs on IP-based relays.
                allow_invalid_cert = true;
                vec![(0, ip)]
            }
            AddressDomain::Name(mx_domain) => {
                if mx_domain.eq_ignore_ascii_case("nauta.cu") {
                    // Special case; We don't want to defederate nauta.cu,
                    // which doesn't support STARTTLS at all.
                    skip_tls = true;
                } else if mx_domain.starts_with('_') {
                    // We use domains starting with `_` for test deployments.
                    // (You can't request a non-wildcard cert for such domain)
                    allow_invalid_cert = true;
                }
                let query = format!("{mx_domain}.");

                match dns_resolver.mx_lookup(query).await {
                    Ok(mx_records) => {
                        let mut hosts: Vec<(u16, String)> = Vec::new();
                        for mx_record in mx_records.answers() {
                            let mx = match mx_record.data {
                                RData::MX(ref mx) => mx,
                                _ => continue,
                            };

                            // Null MX / RFC7505
                            if mx.exchange.is_root() {
                                // From RFC7505 section 3:
                                // > A domain that advertises a null MX MUST NOT
                                // > advertise any other MX RR.
                                // We assume this is the only record and exit early.
                                return Err(
                                    "556 5.1.10 Permanent failure: Recipient address has null MX"
                                        .to_string(),
                                );
                            }

                            let host = mx.exchange.to_string().trim_end_matches('.').to_string();
                            hosts.push((mx.preference, host))
                        }
                        hosts.sort();
                        hosts
                    }
                    Err(e) => {
                        if e.is_no_records_found() {
                            // "implicit MX" as described by section 5.1 of RFC5321
                            // https://datatracker.ietf.org/doc/html/rfc5321#section-5.1
                            log::debug!("No MX record found, using implicit MX: {mx_domain}");
                            vec![(0, mx_domain)]
                        } else if e.is_nx_domain() {
                            return Err(format!("512 Domain {mx_domain} does not exist"));
                        } else {
                            return Err(format!("421 DNS resolution failed for {mx_domain}"));
                        }
                    }
                }
            }
        };

        let tls_config = match skip_tls {
            true => None,
            false => Some(TlsConfig {
                allow_invalid_cert,
                session_cache: tls_resumption_store,
            }),
        };

        // we try sequentially in order of MX preference,
        // but the IPv4 and IPv6 connections (after `smtp_client::send` resolves mx hostname)
        // happens in parallel.
        'try_relay: for (_, mx_host) in mx_hosts {
            let skip_mxdeliv = mxdeliv_unsupported_hosts
                .get(&mx_host)
                .await
                .map(|guard| *guard.value())
                .unwrap_or(false);

            // HTTPS channel
            if skip_mxdeliv {
                log::debug!("Skipping HTTP delivery to host that failed recently: {mx_host}");
            } else {
                match Self::https_delivery(
                    https_client.clone(),
                    mx_host.clone(),
                    &envelope,
                    allow_invalid_cert,
                )
                .await
                {
                    Ok(_) => {
                        return Ok("250 Ok (HTTPS)".to_string());
                    }
                    Err(e) => {
                        log::debug!("HTTPS delivery to {mx_host} failed: {e}");
                    }
                }
            }

            // SMTP channel (fallback)
            match crate::smtp_client::send(
                &mx_host,
                25,
                &envelope,
                &client_hostname,
                tls_config.clone(),
                dns_resolver.clone(),
                smtp_connection_pool.clone(),
            )
            .await
            {
                Ok(_) => {
                    // Switches this host to SMTP for 30 minutes.
                    // Note: this MUST happen only after a successful SMTP delivery,
                    // or otherwise any http error will lock us out of any way to
                    // deliver to a relay with a blocked port 25 for 30 minutes.
                    mxdeliv_unsupported_hosts
                        .insert(mx_host.clone(), true, Duration::from_mins(30))
                        .await;
                    return Ok("250 Ok (SMTP)".to_string());
                }
                Err(error) => {
                    match error {
                        // We only want to try other MX hosts if we encounter a problem
                        // related to connection.
                        // (So we don't spam other servers if the message is actually rejected.)
                        crate::error::Error::Io(io_err) => {
                            log::warn!("I/O error relaying to mail server {mx_host}: {io_err}");
                            continue 'try_relay;
                        }
                        crate::error::Error::ConnectionFailed(_) => {
                            log::warn!("Failed to connect to mail server {mx_host}: {error}");
                            continue 'try_relay;
                        }
                        crate::error::Error::Tls(tls_err) => {
                            log::warn!("TLS error relaying to mail server {mx_host}: {tls_err}");
                            continue 'try_relay;
                        }
                        _ => {
                            log::warn!("Message rejected by mail server {mx_host}: {error}");
                            return Err(error.smtp_response());
                        }
                    }
                }
            }
        }

        Err("421 Failed to connect to any mail server".to_string())
    }

    /// Performs mail delivery to `mx_host` over HTTPS.
    ///
    /// Times out after 60s.
    async fn https_delivery(
        https_client: HttpsClient,
        mx_host: String,
        envelope: &Envelope,
        allow_invalid_cert: bool,
    ) -> Result<(), crate::error::Error> {
        let request: hyper::Request<http_body_util::Full<Bytes>> = {
            let mut builder = hyper::Request::builder()
                .method(hyper::Method::POST)
                .uri(format!("https://{mx_host}/mxdeliv"));

            if !envelope.mail_from.is_empty() {
                builder = builder.header(HEADER_MAIL_FROM, &envelope.mail_from);
            }

            for rcpt_to in &envelope.rcpt_to {
                builder = builder.header(HEADER_RCPT_TO, rcpt_to);
            }

            builder.body(http_body_util::Full::from(envelope.data.clone()))?
        };

        let client = if allow_invalid_cert {
            https_client.relaxed
        } else {
            https_client.secure
        };

        let response = tokio::time::timeout(Duration::from_secs(60), client.request(request))
            .await
            .map_err(|_| crate::error::Error::MailSend {
                context: "HTTPS delivery".to_string(),
                raw_smtp_answer: "[timeout]".to_string(),
            })??;
        if response.status().is_success() {
            Ok(())
        } else {
            let response_body = response.collect().await?.to_bytes();
            Err(crate::error::Error::MailSend {
                context: "HTTPS delivery".to_string(),
                raw_smtp_answer: String::from_utf8_lossy(&response_body).into(),
            })
        }
    }
}

impl Drop for TransportHandler {
    fn drop(&mut self) {
        self.monitor_handle.abort();
    }
}

#[async_trait]
impl SmtpHandler for TransportHandler {
    /// NO-OP
    fn handle_mail(&self, _: &str) -> Result<(), String> {
        Ok(())
    }

    /// NO-OP
    async fn check_data(&self, _: &mut Envelope) -> Result<(), String> {
        Ok(())
    }

    /// NO-OP
    async fn reinject_mail(&self, _: &Envelope) -> Result<(), String> {
        Ok(())
    }

    /// Handles the DATA command and returns LMTP responses as single string.
    ///
    /// Never returns an error, as LMTP response is composite.
    async fn handle_data(&self, envelope: &mut Envelope) -> Result<String, String> {
        let mut domain_rcpts_map = BTreeMap::new();

        for rcpt in &envelope.rcpt_to {
            let domain = AddressDomain::from_str(rcpt)
                // Currently we cancel all transactions if any recipient address is invalid.
                .map_err(|e| e.lmtp_response(envelope.rcpt_to.len()))?;
            domain_rcpts_map
                .entry(domain)
                .or_insert_with(Vec::new)
                .push(rcpt.to_string());
        }

        // one transaction per domain
        let mut transactions = JoinSet::new();
        let mut task_id_domain_map = BTreeMap::new();

        for (rcpt_domain, rcpts) in &domain_rcpts_map {
            let domain_envelope = {
                let mut envelope = envelope.clone();
                envelope.rcpt_to = rcpts.clone();
                envelope
            };
            let task_id = transactions
                .spawn(Self::handle_single_domain(
                    self.tls_resumption_store.clone(),
                    self.smtp_connection_pool.clone(),
                    self.mxdeliv_unsupported_hosts.clone(),
                    self.https_client.clone(),
                    self.dns_resolver.clone(),
                    rcpt_domain.clone(),
                    domain_envelope,
                    self.config.mail_domain.clone(),
                ))
                .id();
            task_id_domain_map.insert(task_id, rcpt_domain);
        }

        let mut rcpt_response_map = BTreeMap::new();
        while let Some(result) = transactions.join_next_with_id().await {
            let domain_response = match result {
                Ok((id, Ok(resp))) | Ok((id, Err(resp))) => {
                    task_id_domain_map.remove(&id).map(|domain| (domain, resp))
                }
                Err(e) => {
                    log::error!("Failed to join task: {e}");
                    task_id_domain_map
                        .remove(&e.id())
                        .map(|domain| (domain, "451 Local error".to_string()))
                }
            };

            if let Some((domain, smtp_response)) = domain_response
                && let Some(rcpts) = domain_rcpts_map.get(domain)
            {
                for rcpt in rcpts {
                    rcpt_response_map.insert(rcpt, smtp_response.clone());
                }
            }
        }

        // compose lmtp response...
        let ordered_responses: Vec<String> = envelope
            .rcpt_to
            .iter()
            .map(|rcpt| {
                rcpt_response_map
                    .remove(rcpt)
                    .unwrap_or_else(|| "451 Local error".to_string())
            })
            .collect();

        Ok(ordered_responses.join("\r\n"))
    }
}
