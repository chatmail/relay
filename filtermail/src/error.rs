//! Error types.

/// Error type for filtermail.
#[derive(Debug, thiserror::Error)]
#[non_exhaustive]
pub enum Error {
    #[error("Chatmail config is invalid: {0}")]
    Config(#[from] serini::Error),
    #[error(transparent)]
    Io(#[from] std::io::Error),
    #[error("OpenPGP packet header is truncated - can't validate!")]
    TruncatedHeader,
    #[error("Unable to send email, Error during {context}, server said: {raw_smtp_answer}")]
    MailSend {
        context: String,
        raw_smtp_answer: String,
    },
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
            _ => "451 Local error".to_string(),
        }
    }
}
