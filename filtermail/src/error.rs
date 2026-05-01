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
    Resolve(#[from] hickory_resolver::ResolveError),
    #[error("OpenPGP packet header is truncated - can't validate!")]
    TruncatedHeader,
    #[error("Unable to send email, Error during {context}, server said: {raw_smtp_answer}")]
    MailSend {
        context: String,
        raw_smtp_answer: String,
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
        match self {
            // We transparently pass postfix/milter errors reported on reinjection
            Error::MailSend {
                raw_smtp_answer, ..
            } => raw_smtp_answer.clone(),
            Error::TruncatedHeader => self.to_string(),
            Error::InvalidEmailAddress(address) => format!("500 Invalid email address: {address}"),
            _ => "451 Local error".to_string(),
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
