//! A simplified SMTP server implementation for internal communication.

use crate::utils::extract_address;
use async_trait::async_trait;
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::{TcpListener, TcpStream};

/// Represents an SMTP envelope with sender, recipients, and raw message data.
#[derive(Debug, Clone)]
pub struct Envelope {
    pub mail_from: String,
    pub rcpt_to: Vec<String>,
    pub data: Vec<u8>,
}

/// Trait defining the SMTP handler interface.
#[async_trait]
pub trait SmtpHandler: Send + Sync {
    /// Handles the MAIL FROM command.
    fn handle_mail(&self, address: &str) -> Result<(), String>;

    /// Checks the DATA command before reinjection.
    fn check_data(&self, envelope: &Envelope) -> Result<(), String>;

    /// Reinjects the mail back to postfix.
    async fn reinject_mail(&self, envelope: &Envelope) -> Result<(), String>;

    /// Handles the DATA command.
    async fn handle_data(&self, envelope: &Envelope) -> Result<String, String> {
        log::info!("handle_DATA before-queue");
        self.check_data(envelope)?;
        self.reinject_mail(envelope).await.map_err(|e| {
            log::warn!("Failed to reinject mail: {}", e);
            e
        })?;
        Ok("250 OK".to_string())
    }
}

/// Runs the SMTP server on the specified address with the given handler and maximum message size.
pub async fn run_smtp_server<H>(
    addr: &str,
    handler: Arc<H>,
    max_size: usize,
) -> Result<(), Box<dyn std::error::Error>>
where
    H: SmtpHandler + 'static,
{
    let listener = TcpListener::bind(addr).await?;
    // message for backward compatibility with chatmaild tests.
    log::info!("entering serving loop");

    loop {
        let (socket, _) = listener.accept().await?;
        let handler = handler.clone();
        tokio::spawn(async move {
            if let Err(e) = handle_connection(socket, handler, max_size).await {
                log::error!("Error handling connection: {}", e);
            }
        });
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
    let (reader, mut writer) = socket.into_split();
    let mut reader = BufReader::new(reader);
    let mut line = String::new();

    writer.write_all(b"220 filtermail SMTP\r\n").await?;

    let mut envelope = Envelope {
        mail_from: String::new(),
        rcpt_to: Vec::new(),
        data: Vec::new(),
    };

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
            log::warn!("Malformed command without CRLF ending! Closing connection.");
            break 'connection;
        };

        log::debug!("Received: {}", cmd);

        if cmd.to_uppercase().starts_with("HELO") || cmd.to_uppercase().starts_with("EHLO") {
            writer.write_all(b"250 OK\r\n").await?;
        } else if cmd.to_uppercase().starts_with("MAIL FROM:") {
            if let Some(from) = extract_address(cmd) {
                match handler.handle_mail(&from) {
                    Ok(_) => {
                        envelope.mail_from = from;
                        writer.write_all(b"250 OK\r\n").await?;
                    }
                    Err(e) => {
                        writer.write_all(format!("{}\r\n", e).as_bytes()).await?;
                        break 'connection;
                    }
                }
            } else {
                log::debug!("Invalid MAIL FROM command. Can't extract address.");
                writer
                    .write_all(b"500 Invalid address in MAIL FROM\r\n")
                    .await?;
            }
        } else if cmd.to_uppercase().starts_with("RCPT TO:") {
            if let Some(to) = extract_address(cmd) {
                envelope.rcpt_to.push(to);
                writer.write_all(b"250 OK\r\n").await?;
            }
        } else if cmd.to_uppercase().starts_with("DATA") {
            writer
                .write_all(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                .await?;
            let mut data = Vec::new();
            let mut data_line = String::new();
            'data_read: loop {
                data_line.clear();
                reader.read_line(&mut data_line).await?;

                if data_line == ".\r\n" {
                    break 'data_read;
                }

                if !data_line.ends_with("\r\n") {
                    log::warn!("Malformed DATA line without CRLF ending! Closing connection.");
                    break 'connection;
                }

                data.extend_from_slice(data_line.as_bytes());

                if data.len() > max_size {
                    writer
                        .write_all(b"552 Message exceeds maximum size\r\n")
                        .await?;
                    break 'connection;
                }
            }

            envelope.data = data;

            // Process the message
            match handler.handle_data(&envelope).await {
                Ok(response) => {
                    log::debug!("Sent: {}", response);
                    writer
                        .write_all(format!("{}\r\n", response).as_bytes())
                        .await?;
                }
                Err(e) => {
                    log::debug!("Sent: {}", e);
                    writer.write_all(format!("{}\r\n", e).as_bytes()).await?;
                }
            }

            envelope = Envelope {
                mail_from: String::new(),
                rcpt_to: Vec::new(),
                data: Vec::new(),
            };
        } else if cmd.to_uppercase().starts_with("QUIT") {
            writer.write_all(b"221 OK\r\n").await?;
            break 'connection;
        } else if cmd.to_uppercase().starts_with("RSET") {
            envelope = Envelope {
                mail_from: String::new(),
                rcpt_to: Vec::new(),
                data: Vec::new(),
            };
            writer.write_all(b"250 OK\r\n").await?;
        } else if cmd.to_uppercase().starts_with("NOOP") {
            writer.write_all(b"250 OK\r\n").await?;
        } else {
            writer.write_all(b"500 Command not recognized\r\n").await?;
        }
    }

    Ok(())
}
