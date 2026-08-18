use crate::tls;
use hyper::body::Bytes;
use hyper_rustls::HttpsConnector;
use hyper_util::client::legacy::connect::HttpConnector;
use std::sync::Arc;
use tokio_rustls::rustls;

/// Cheaply clonable HTTPS client.
///
/// Holds regular secure variant and relaxed - without certificate verification.
///
/// Connection pool handled internally by [`hyper_util::client::legacy::Client`].
#[derive(Clone)]
pub(crate) struct HttpsClient {
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
    pub fn new(
        tls_resumption_store: Arc<rustls::client::ClientSessionMemoryCache>,
    ) -> Result<Self, crate::error::Error> {
        let tls_client_config = tls::configure_rustls(tls_resumption_store.clone(), false)?;
        let https_connector = hyper_rustls::HttpsConnectorBuilder::new()
            .with_tls_config(tls_client_config)
            .https_only()
            .enable_http1()
            .enable_http2()
            .build();
        let https_client =
            hyper_util::client::legacy::Client::builder(hyper_util::rt::TokioExecutor::new())
                .build(https_connector);

        let tls_client_config_relaxed = tls::configure_rustls(tls_resumption_store, true)?;
        let https_connector_relaxed = hyper_rustls::HttpsConnectorBuilder::new()
            .with_tls_config(tls_client_config_relaxed)
            .https_only()
            .enable_http1()
            .enable_http2()
            .build();
        let https_client_relaxed =
            hyper_util::client::legacy::Client::builder(hyper_util::rt::TokioExecutor::new())
                .build(https_connector_relaxed);

        Ok(Self {
            secure: https_client,
            relaxed: https_client_relaxed,
        })
    }
}
