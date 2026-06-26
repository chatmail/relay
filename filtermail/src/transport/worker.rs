use crate::config::Config;
use crate::smtp_client::{SmtpConnectionPool, TlsConfig};
use crate::smtp_responses::{OK_HTTPS_250, OK_SMTP_250};
use crate::smtp_server::Envelope;
use crate::tcp::{TcpConnect, TcpStreamTrait};
use crate::transport::{HEADER_MAIL_FROM, HEADER_RCPT_TO, https_client::HttpsClient};
use crate::utils::{AddressDomain, build_resolver};
use hickory_resolver::TokioResolver;
use hickory_resolver::proto::rr::RData;
use http_body_util::BodyExt;
use hyper::body::Bytes;
use parking_lot::RwLock;
use std::collections::BTreeMap;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::mpsc::OwnedPermit;
use tokio::sync::{mpsc, oneshot};
use tokio::task;
use tokio::task::JoinHandle;
use tokio_rustls::rustls;

#[cfg(not(test))]
const SMTP_PORT: u16 = 25;
#[cfg(not(test))]
const SMTP_SKIP_TLS: bool = false;

#[cfg(test)]
const SMTP_PORT: u16 = 10025;
#[cfg(test)]
const SMTP_SKIP_TLS: bool = true;

/// Message queue size per [`Worker`].
///
/// If a queue to a single destination reaches this limit,
/// all new messages will be immediately deferred.
const PER_DESTINATION_QUEUE_SIZE: usize = 30;

type SMTPResponse = Result<String, String>;

pub struct WorkerPool<S: TcpConnect> {
    inner: RwLock<BTreeMap<AddressDomain, Arc<Worker>>>,
    client_hostname: String,
    smtp_connection_pool: Arc<SmtpConnectionPool<S>>,
    mxdeliv_unsupported_hosts: Arc<retainer::Cache<String, ()>>,
    monitor_handle: JoinHandle<()>,
    dns_resolver: Arc<TokioResolver>,
    queue_size: usize,
}

impl<S> WorkerPool<S>
where
    S: TcpStreamTrait + TcpConnect,
    S::ConnectionContext: Default,
{
    pub fn new(config: Config) -> Result<Self, crate::error::Error> {
        let dns_resolver = Arc::new(build_resolver()?);

        let mxdeliv_cache = Arc::new(retainer::Cache::new());
        let mxdeliv_cache_clone = mxdeliv_cache.clone();

        let monitor_handle = tokio::spawn(async move {
            mxdeliv_cache_clone
                .monitor(4, 0.25, Duration::from_secs(10))
                .await
        });

        Ok(Self {
            inner: Default::default(),
            client_hostname: config.mail_domain,
            dns_resolver,
            smtp_connection_pool: SmtpConnectionPool::<S>::new(Default::default()),
            mxdeliv_unsupported_hosts: mxdeliv_cache,
            monitor_handle,
            queue_size: PER_DESTINATION_QUEUE_SIZE,
        })
    }

    /// Same as [`Self::new`], but lets you set the size of the queue.
    ///
    /// Used only for tests.
    #[cfg(test)]
    pub fn with_queue_size(config: Config, queue_size: usize) -> Result<Self, crate::error::Error> {
        let mut this = Self::new(config)?;
        this.queue_size = queue_size;
        Ok(this)
    }

    fn get_or_create_worker(&self, destination: &AddressDomain) -> Arc<Worker> {
        // NOTE: these locks are blocking, but critical section here is quite small and
        // shouldn't cause issues in async code.
        // NOTE: read() returns a guard that is dropped before the match statement.
        // This must be ensured or else, the write() line would cause a deadlock.
        let worker = {
            let mut worker = {
                let map = self.inner.read();
                map.get(destination).cloned()
            };
            // Remove (and re-create) worker if it finished/crashed.
            // In reality, this should never happen.
            if let Some(w) = &worker
                && w.handle.is_finished()
            {
                log::error!("Worker for destination {destination} crashed! Restarting...",);
                worker = None;
                {
                    let mut map = self.inner.write();
                    map.remove(destination);
                }
            };
            worker
        };

        match worker {
            Some(worker) => worker,
            None => {
                // Worker for this destination wasn't spawned yet.
                let (tx, rx) = mpsc::channel(self.queue_size);
                let handle = tokio::spawn(Worker::run(
                    destination.clone(),
                    rx,
                    self.client_hostname.clone(),
                    self.smtp_connection_pool.clone(),
                    self.mxdeliv_unsupported_hosts.clone(),
                    self.dns_resolver.clone(),
                ));
                log::trace!("Worker {} spawned", handle.id());
                let worker = Arc::new(Worker { tx, handle });

                self.inner
                    .write()
                    .insert(destination.clone(), worker.clone());
                worker
            }
        }
    }

    /// Tries to get an [`OwnedPermit`] to the worker for specified destination.
    ///
    /// Returns [`None`] if the worker's queue is full.
    pub fn get_permit(&self, destination: &AddressDomain) -> Option<OwnedPermit<WorkerMessage>> {
        let worker = self.get_or_create_worker(destination);
        worker.tx.clone().try_reserve_owned().ok()
    }
}

impl<S: TcpConnect> Drop for WorkerPool<S> {
    fn drop(&mut self) {
        self.monitor_handle.abort();
    }
}

#[derive(Debug)]
pub struct Worker {
    pub tx: mpsc::Sender<WorkerMessage>,
    handle: JoinHandle<Result<(), crate::error::Error>>,
}

impl Drop for Worker {
    fn drop(&mut self) {
        self.handle.abort();
    }
}

impl Worker {
    pub async fn run<S>(
        destination: AddressDomain,
        mut rx: mpsc::Receiver<WorkerMessage>,
        client_hostname: String,
        smtp_connection_pool: Arc<SmtpConnectionPool<S>>,
        mxdeliv_unsupported_hosts: Arc<retainer::Cache<String, ()>>,
        dns_resolver: Arc<TokioResolver>,
    ) -> Result<(), crate::error::Error>
    where
        S: TcpStreamTrait + TcpConnect,
    {
        let worker_id = task::try_id()
            .map(|id| id.to_string())
            .unwrap_or("?".to_string());

        log::info!("Starting worker {worker_id} for destination {destination}");

        let tls_resumption_store = Arc::new(rustls::client::ClientSessionMemoryCache::new(256));
        let https_client = HttpsClient::new(tls_resumption_store.clone())?;

        while let Some(message) = rx.recv().await {
            log::trace!(
                "Worker {worker_id} received a message from {}",
                message.envelope.mail_from
            );
            let result = Self::handle_single_domain(
                tls_resumption_store.clone(),
                smtp_connection_pool.clone(),
                mxdeliv_unsupported_hosts.clone(),
                https_client.clone(),
                dns_resolver.clone(),
                destination.clone(),
                message.envelope,
                client_hostname.clone(),
            )
            .await;
            if message.response_tx.send(result).is_err() {
                log::error!(
                    "Worker {worker_id} ({destination}) failed to send response to transport handler."
                );
            };
        }

        Ok(())
    }

    /// Handles a single email transaction for a single recipient domain.
    #[expect(clippy::too_many_arguments)]
    async fn handle_single_domain<S>(
        tls_resumption_store: Arc<rustls::client::ClientSessionMemoryCache>,
        smtp_connection_pool: Arc<SmtpConnectionPool<S>>,
        mxdeliv_unsupported_hosts: Arc<retainer::Cache<String, ()>>,
        https_client: HttpsClient,
        dns_resolver: Arc<TokioResolver>,
        domain: AddressDomain,
        envelope: Envelope,
        client_hostname: String,
    ) -> Result<String, String>
    where
        S: TcpStreamTrait + TcpConnect,
    {
        let mut allow_invalid_cert = false;
        let mut skip_tls = SMTP_SKIP_TLS; // only respected by smtp channel

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

        let mut last_error = None;

        // we try sequentially in order of MX preference,
        // but the IPv4 and IPv6 connections (after `smtp_client::send` resolves mx hostname)
        // happens in parallel.
        'try_relay: for (_, mx_host) in mx_hosts {
            let skip_mxdeliv = mxdeliv_unsupported_hosts
                .get(&mx_host)
                .await
                .map(|guard| *guard.value())
                .is_some();

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
                        return Ok(OK_HTTPS_250.to_string());
                    }
                    Err(e) => {
                        log::debug!("HTTPS delivery to {mx_host} failed: {e}");
                    }
                }
            }

            // SMTP channel (fallback)
            let client_config = crate::smtp_client::ClientConfig {
                client_hostname: &client_hostname,
                tls_config: tls_config.clone(),
                lmtp: false,
            };
            match crate::smtp_client::send(
                &mx_host,
                SMTP_PORT,
                &envelope,
                client_config,
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
                        .insert(mx_host.clone(), (), Duration::from_mins(30))
                        .await;
                    return Ok(OK_SMTP_250.to_string());
                }
                Err(error) => {
                    match &error {
                        // We only want to try other MX hosts if we encounter a problem
                        // related to connection.
                        // (So we don't spam other servers if the message is actually rejected.)
                        crate::error::Error::Io(_)
                        | crate::error::Error::ConnectionFailed(_)
                        | crate::error::Error::Tls(_) => {
                            // Make sure we quickly retry HTTP if SMTP failed to connect
                            mxdeliv_unsupported_hosts.remove(&mx_host).await;
                            log::warn!(
                                "Connection error relaying to mail server {mx_host}: {error}"
                            );
                            last_error = Some((error.smtp_response(), mx_host.clone()));
                            continue 'try_relay;
                        }
                        crate::error::Error::MailSend { .. } => {
                            log::warn!("Message rejected by mail server {mx_host}: {error}");
                            return Err(error.smtp_response());
                        }
                        _ => {
                            log::warn!(
                                "Unexpected error while delivering to mail server {mx_host}: {error}"
                            );
                            return Err(format!(
                                "{} (while attempting delivery to {mx_host})",
                                error.smtp_response()
                            ));
                        }
                    }
                }
            }
        }

        let (error, mx_host) = last_error.unwrap_or(("?".to_string(), "?".to_string()));
        Err(format!(
            "421 Failed to connect to any mail server; last attempt to {mx_host}: {error}"
        ))
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
                host: mx_host.clone(),
            })??;
        if response.status().is_success() {
            Ok(())
        } else {
            let response_body = response.collect().await?.to_bytes();
            Err(crate::error::Error::MailSend {
                context: "HTTPS delivery".to_string(),
                raw_smtp_answer: String::from_utf8_lossy(&response_body).into(),
                host: mx_host,
            })
        }
    }
}

pub struct WorkerMessage {
    pub envelope: Envelope,
    pub response_tx: oneshot::Sender<SMTPResponse>,
}

impl WorkerMessage {
    pub fn new(envelope: Envelope) -> (Self, oneshot::Receiver<SMTPResponse>) {
        let (response_tx, response_rx) = oneshot::channel();
        (
            Self {
                envelope,
                response_tx,
            },
            response_rx,
        )
    }
}
