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
}
