//! A simplified SMTP server implementation for internal communication.

use crate::smtp_responses::OK_250;
use crate::utils::{extract_address, log_eml};
use async_trait::async_trait;
use memchr::{Memchr, memmem};
use std::fmt::Debug;
use std::sync::Arc;
use std::time::Duration;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader, BufWriter};
use tokio::net::{TcpListener, TcpStream};

/// Represents an SMTP envelope with sender, recipients, and raw message data.
#[derive(Debug, Default, Clone)]
pub struct Envelope {
    pub mail_from: String,
    pub rcpt_to: Vec<String>,
    /// Mail data as transmitted over SMTP/LMTP.
    ///
    /// Described in <https://www.rfc-editor.org/rfc/rfc5321.html#section-2.3.9>.
    ///
    /// It MUST end with `<CRLF>`, contain no bare `<CR>` or `<LF>`
    /// and have all `<CRLF>.` sequences escaped with `.` according to
    /// <https://www.rfc-editor.org/rfc/rfc5321.html#section-4.5.2>.
    pub data: Vec<u8>,
}

/// Represent an ongoing SMTP transaction.
///
/// Every new connection starts with an empty envelope and handler state.
/// A RSET command starts a new transaction, which clears the envelope and state.
#[derive(Debug, Default)]
pub struct Transaction<S: Debug + Default> {
    pub envelope: Envelope,
    pub state: S,
}

/// Checks if mail data is valid.
fn is_valid_data(data: &[u8]) -> bool {
    // DATA must end with <CRLF>.
    //
    // Otherwise it is not possible to reinject it as is into SMTP/LMTP
    // without adding <CRLF> at the end and modifying the message.
    if !data.ends_with(b"\r\n") {
        return false;
    }

    // Check for bare `<CR>` and `<LF>`.
    // <https://www.rfc-editor.org/rfc/rfc5321.html#section-2.3.8>
    for pos in Memchr::new(b'\r', data) {
        if data.get(pos + 1) != Some(&b'\n') {
            return false;
        }
    }
    for pos in Memchr::new(b'\n', data) {
        if pos == 0 || data.get(pos - 1) != Some(&b'\r') {
            return false;
        }
    }

    // Do not allow unescaped `.`.
    if data.starts_with(b".\r\n") || memmem::find(data, b"\r\n.\r\n").is_some() {
        return false;
    }

    true
}

/// Trait defining the SMTP handler interface.
#[async_trait]
pub trait SmtpHandler: Send + Sync {
    /// Transaction state type associated with this handler.
    type State: Debug + Default + Send;

    /// Checks the DATA command before reinjection.
    ///
    /// Can optionally modify the envelope before reinjection.
    ///
    /// Default implementation is no-op.
    async fn check_data(&self, _transaction: &mut Transaction<Self::State>) -> Result<(), String> {
        Ok(())
    }

    /// Reinjects the mail back to postfix.
    ///
    /// Default implementation is no-op.
    async fn reinject_mail(&self, _transaction: &Transaction<Self::State>) -> Result<(), String> {
        Ok(())
    }

    /// Handles the MAIL FROM command.
    ///
    /// Default implementation is no-op.
    fn handle_mail_from(&self, _address: &str) -> Result<(), String> {
        Ok(())
    }

    /// Handles the RCPT TO command.
    ///
    /// Default implementation is no-op.
    fn handle_rcpt_to(
        &self,
        _address: &str,
        _transaction: &mut Transaction<Self::State>,
    ) -> Result<(), String> {
        Ok(())
    }

    /// Handles the DATA command. Called after receiving DATA, before receiving actual data.
    ///
    /// Default implementation is no-op.
    fn handle_data_start(&self, _transaction: &Transaction<Self::State>) -> Result<(), String> {
        Ok(())
    }

    /// Handles the end of DATA command. Called after receiving the final dot.
    async fn handle_data_dot(
        &self,
        transaction: &mut Transaction<Self::State>,
    ) -> Result<String, String> {
        log::debug!("handle_DATA before-queue");

        // Check if the DATA is valid
        // before doing any custom checks.
        //
        // We are not going to normalize newlines
        // and escape the dots in the mail data.
        // If mail data turned out to be invalid, reject immediately.
        if !is_valid_data(&transaction.envelope.data) {
            return Err("500 Invalid DATA".to_string());
        }

        self.check_data(transaction).await?;
        if transaction.envelope.rcpt_to.is_empty() {
            log::warn!("Dropping mail; All recipients disabled.");
            return Ok(OK_250.to_string());
        }
        self.reinject_mail(transaction).await.map_err(|e| {
            log::warn!("Failed to reinject mail: {e}");
            e
        })?;
        Ok("OK_250".to_string())
    }
}

/// Runs the SMTP server on the specified address with the given handler and maximum message size.
pub async fn run_smtp_server<H>(
    addr: &impl tokio::net::ToSocketAddrs,
    handler: Arc<H>,
    max_size: usize,
) -> Result<(), crate::error::Error>
where
    H: SmtpHandler + 'static,
{
    let listener = TcpListener::bind(addr).await?;
    // message for backward compatibility with chatmaild tests.
    log::info!("entering serving loop");

    loop {
        match listener.accept().await {
            Ok((socket, _peer_addr)) => {
                // Disable Nagle's algorithm.
                socket.set_nodelay(true)?;

                let handler = handler.clone();
                tokio::spawn(async move {
                    if let Err(e) = handle_connection(socket, handler, max_size).await {
                        log::error!("Error handling connection: {e}");
                    }
                });
            }
            Err(e) => {
                log::error!("Error accepting connection: {e}");

                // Sleep to avoid busy looping in case we ran into file descriptor limit.
                tokio::time::sleep(Duration::from_secs(10)).await;
            }
        }
    }
}

/// Handles an individual SMTP connection.
async fn handle_connection<H>(
    socket: TcpStream,
    handler: Arc<H>,
    max_size: usize,
) -> Result<(), Box<dyn std::error::Error>>
where
    H: SmtpHandler,
{
    let (reader, writer) = socket.into_split();
    let mut reader = BufReader::new(reader);
    let mut writer = BufWriter::new(writer);
    let mut line = String::new();

    writer.write_all(b"220 filtermail SMTP\r\n").await?;
    writer.flush().await?;

    let mut transaction = Transaction::default();

    'connection: loop {
        line.clear();
        let n = reader.read_line(&mut line).await?;
        if n == 0 {
            break 'connection;
        }

        // Remove CRLF
        // Note: this will kill the connection if any line doesn't end with CRLF.
        // This is intentional as stray LF most likely means an attempt to exploit the server.
        let Some(cmd) = line.strip_suffix("\r\n") else {
            log::warn!(
                "Malformed command without CRLF ending! Received: {line:?} Closing connection."
            );
            break 'connection;
        };

        log::debug!("Received: {cmd}");

        if cmd.to_uppercase().starts_with("HELO") {
            writer.write_all(b"250-filtermail\r\n250 OK\r\n").await?;
            writer.flush().await?;
        } else if cmd.to_uppercase().starts_with("EHLO")
            // We support LMTP, but it's not validated;
            // service that expects LMTP will send LMTP responses no matter the greeting.
            // Sufficient for our internal use case.
            || cmd.to_uppercase().starts_with("LHLO")
        {
            writer
                .write_all(b"250-filtermail\r\n250-8BITMIME\r\n250 OK\r\n")
                .await?;
            writer.flush().await?;
        } else if cmd.to_uppercase().starts_with("MAIL FROM:<>") {
            // bounce message
            transaction.envelope.mail_from = String::new();
            writer.write_all(format!("{OK_250}\r\n").as_bytes()).await?;
            writer.flush().await?;
        } else if cmd.to_uppercase().starts_with("MAIL FROM:") {
            if let Some(from) = extract_address(cmd) {
                if let Err(e) = handler.handle_mail_from(&from) {
                    writer.write_all(format!("{}\r\n", e).as_bytes()).await?;
                    writer.flush().await?;
                    continue 'connection;
                }
                transaction.envelope.mail_from = from;
                writer.write_all(format!("{OK_250}\r\n").as_bytes()).await?;
                writer.flush().await?;
            } else {
                log::warn!("Invalid MAIL FROM command. Can't extract address. Received: {cmd}");
                writer
                    .write_all(b"500 Invalid address in MAIL FROM\r\n")
                    .await?;
                writer.flush().await?;
            }
        } else if cmd.to_uppercase().starts_with("RCPT TO:") {
            if let Some(to) = extract_address(cmd) {
                if let Err(e) = handler.handle_rcpt_to(&to, &mut transaction) {
                    writer.write_all(format!("{}\r\n", e).as_bytes()).await?;
                    writer.flush().await?;
                    continue 'connection;
                }
                transaction.envelope.rcpt_to.push(to);
                writer.write_all(format!("{OK_250}\r\n").as_bytes()).await?;
                writer.flush().await?;
            }
        } else if cmd.to_uppercase().starts_with("DATA") {
            if let Err(e) = handler.handle_data_start(&transaction) {
                writer.write_all(format!("{}\r\n", e).as_bytes()).await?;
                writer.flush().await?;
                continue 'connection;
            }
            writer
                .write_all(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                .await?;
            writer.flush().await?;
            let mut data = Vec::new();
            let mut data_line = String::new();
            'data_read: loop {
                data_line.clear();
                if reader.read_line(&mut data_line).await? == 0 {
                    log::warn!("Unexpected EoF while receiving DATA! Closing connection.");
                    break 'connection;
                }

                if data_line == ".\r\n" {
                    break 'data_read;
                }

                if !data_line.ends_with("\r\n") {
                    log::warn!("Malformed DATA line without CRLF ending! Closing connection.");
                    data.extend_from_slice(data_line.as_bytes());
                    let eml_path = log_eml("malformed-data", &data)
                        .await
                        .map(|path| path.to_string_lossy().to_string())
                        .unwrap_or_else(|e| {
                            log::error!("Failed to save rejected message to file: {e}");
                            "ERR".to_string()
                        });
                    log::info!("Rejected message stored at: {eml_path}");
                    break 'connection;
                }

                data.extend_from_slice(data_line.as_bytes());

                if data.len() > max_size {
                    writer
                        .write_all(b"552 Message exceeds maximum size\r\n")
                        .await?;
                    writer.flush().await?;
                    continue 'connection;
                }
            }

            transaction.envelope.data = data;

            // Process the message
            match handler.handle_data_dot(&mut transaction).await {
                Ok(response) => {
                    log::debug!("Sent: {response}");
                    writer
                        .write_all(format!("{}\r\n", response).as_bytes())
                        .await?;
                    writer.flush().await?;
                }
                Err(e) => {
                    log::debug!("Sent: {e}");
                    writer.write_all(format!("{}\r\n", e).as_bytes()).await?;
                    writer.flush().await?;
                }
            }

            transaction = Transaction::default();
        } else if cmd.to_uppercase().starts_with("QUIT") {
            writer.write_all(b"221 OK\r\n").await?;
            writer.flush().await?;
            break 'connection;
        } else if cmd.to_uppercase().starts_with("RSET") {
            transaction = Transaction::default();
            writer.write_all(format!("{OK_250}\r\n").as_bytes()).await?;
            writer.flush().await?;
        } else if cmd.to_uppercase().starts_with("NOOP") {
            writer.write_all(format!("{OK_250}\r\n").as_bytes()).await?;
            writer.flush().await?;
        } else {
            writer.write_all(b"500 Command not recognized\r\n").await?;
            writer.flush().await?;
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use rstest::*;

    #[rstest]
    #[case(b"", false)]
    #[case(b".", false)]
    #[case(b"Hello!\n", false)]
    #[case(b"Hello!\n\r", false)]
    #[case(b"Hello\nworld!\r\n", false)]
    #[case(b"Hello!\r\n\n", false)]
    #[case(b"Hello\r\n.\r\n", false)]
    #[case(b"Hello!\r\n .\r\n", true)]
    #[case(b"Hello!\r\n..\r\n", true)]
    #[case(b"Hello!\r\n", true)]
    #[case(b"Hello\r\n.world\r\n", true)]
    #[case(b"Hello!\r\r\n", false)]
    #[case(b"Hello!\r\r\n\n", false)]
    #[case(b"Hello\rworld!\r\n", false)]
    #[case(b"\n", false)]
    #[case(b"\nHello\r\n", false)]
    #[case(b"\r", false)]
    #[case(b".\r\n", false)]
    #[case(b".\r\nHello\r\n", false)]
    #[case(b"..\r\n.\r\n", false)]
    #[case(b".\r\n..\r\n", false)]
    #[case(b"\r\n.\r\n", false)]
    #[case(b"..\r\n..\r\n", true)]
    #[case(b" .\r\n", true)]
    #[case(b"..\r\n", true)]
    #[case(b"\r\n", true)]
    fn test_is_valid_data(#[case] data: &[u8], #[case] expected: bool) {
        assert_eq!(is_valid_data(data), expected, "{data:?}");
    }
}
