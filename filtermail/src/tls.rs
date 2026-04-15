//! TLS support.
use std::sync::Arc;
use tokio::io::{AsyncRead, AsyncWrite};
use tokio_rustls::rustls::client::ClientSessionMemoryCache;
use tokio_rustls::{TlsStream, rustls};

mod danger;
use danger::NoCertificateVerification;

pub async fn wrap_rustls<IO>(
    hostname: &str,
    stream: IO,
    resumption_store: Arc<ClientSessionMemoryCache>,
    dangerous_no_cert_verification: bool,
) -> Result<TlsStream<IO>, crate::error::Error>
where
    IO: AsyncRead + AsyncWrite + Unpin,
{
    let mut root_cert_store = rustls::RootCertStore::empty();
    root_cert_store.extend(webpki_roots::TLS_SERVER_ROOTS.iter().cloned());

    let mut config = rustls::ClientConfig::builder()
        .with_root_certificates(root_cert_store)
        .with_no_client_auth();

    // Enable TLS 1.3 session resumption
    // as defined in <https://www.rfc-editor.org/rfc/rfc8446#section-2.2>.
    //
    // Obsolete TLS 1.2 mechanisms defined in RFC 5246
    // and RFC 5077 have worse security
    // and are not worth increasing
    // attack surface: <https://words.filippo.io/we-need-to-talk-about-session-tickets/>.
    config.resumption = rustls::client::Resumption::store(resumption_store)
        .tls12_resumption(rustls::client::Tls12Resumption::Disabled);

    if dangerous_no_cert_verification {
        config
            .dangerous()
            .set_certificate_verifier(Arc::new(NoCertificateVerification::default()));
    }

    let tls = tokio_rustls::TlsConnector::from(Arc::new(config));
    let name = rustls::pki_types::ServerName::try_from(hostname)?.to_owned();
    let tls_stream = tls.connect(name, stream).await?;
    Ok(tls_stream.into())
}
