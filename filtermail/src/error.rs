//! Error types.

use tokio_rustls::rustls;

/// Error type for filtermail.
#[derive(Debug, thiserror::Error)]
#[non_exhaustive]
pub enum Error {
    #[error("Chatmail config is invalid: {0}")]
    Config(#[from] serini::Error),
    #[error(transparent)]
    Io(#[from] std::io::Error),
    #[error(transparent)]
    Resolve(#[from] hickory_resolver::net::NetError),
    #[error("OpenPGP packet header is truncated - can't validate!")]
    TruncatedHeader,
    #[error("Unable to send email, Error during {context}, host {host} said: {raw_smtp_answer}")]
    MailSend {
        context: String,
        raw_smtp_answer: String,
        host: String,
    },
    #[error("Invalid email address: {0}")]
    InvalidEmailAddress(String),
    #[error("Failed to connect to any of the following addresses: {0:?}")]
    ConnectionFailed(Vec<String>),
    #[error(transparent)]
    Tls(#[from] rustls::Error),
    #[error(transparent)]
    InvalidDnsName(#[from] rustls::pki_types::InvalidDnsNameError),
    #[error(transparent)]
    Hyper(#[from] hyper::Error),
    #[error(transparent)]
    HyperHttp(#[from] hyper::http::Error),
    #[error(transparent)]
    HyperClient(#[from] hyper_util::client::legacy::Error),
}

impl Error {
    /// Formats [`Error`] as an SMTP response.
    pub fn smtp_response(&self) -> String {
        macro_rules! format_smtp {
            ($code:expr) => {
                format!("{} {}", $code, self.to_string())
            };
        }

        match self {
            // Errors returned by server we connect to are forwarded.
            // We add "(forwarded from ...)" to distinguish these from our local errors.
            Error::MailSend {
                raw_smtp_answer,
                host,
                ..
            } => format!("{raw_smtp_answer} (forwarded from {host})"),

            // Permanent errors
            Error::TruncatedHeader => format_smtp!("554"),
            Error::InvalidEmailAddress(_) => format_smtp!("553"),
            Error::InvalidDnsName(_) => format_smtp!("501"),

            // Transient errors
            Error::ConnectionFailed(_) => format_smtp!("450"),
            // We don't want to leak chatmail.ini config and other local error details.
            Error::Config(_) => "451 Filtermail misconfigured; contact admin".to_string(),
            Error::Io(_) => "451 I/O error".to_string(),
            Error::Tls(_) => "451 TLS error".to_string(),
            Error::Resolve(_) => "451 Resolver error".to_string(),
            Error::Hyper(_) | Error::HyperHttp(_) | Error::HyperClient(_) => {
                "451 HTTP error".to_string()
            }
        }
    }

    /// Same as [`smtp_response`](Self::smtp_response) but formats the same response
    /// for each recipient, as expected by LMTP.
    pub fn lmtp_response(&self, recipient_count: usize) -> String {
        let response = self.smtp_response();
        std::iter::repeat_n(response, recipient_count)
            .collect::<Vec<_>>()
            .join("\r\n")
    }
}
