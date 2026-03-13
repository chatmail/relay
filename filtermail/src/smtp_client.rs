use crate::smtp_server::Envelope;
use std::net::SocketAddr;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufStream};
use tokio::net::TcpSocket;

/// Sends an email using an SMTP server at `smtp_addr`.
pub async fn send(smtp_addr: SocketAddr, envelope: &Envelope) -> Result<(), crate::error::Error> {
    let socket = TcpSocket::new_v4()?;

    // Disable Nagle's algorithm.
    socket.set_nodelay(true)?;

    let stream = socket.connect(smtp_addr).await?;

    let mut buf_stream = BufStream::new(stream);
    let mut response = String::new();

    macro_rules! smtp_write {
        ($command: expr) => {
            buf_stream.write_all($command).await?;
            buf_stream.flush().await?;
        };
    }

    macro_rules! smtp_read {
        ($context:expr, $expected_code:expr) => {
            buf_stream.read_line(&mut response).await?;
            if !response.starts_with($expected_code) {
                return Err(crate::error::Error::MailSend {
                    context: $context.to_string(),
                    raw_smtp_answer: response.clone(),
                });
            }
            response.clear();
        };
    }

    macro_rules! smtp_cmd {
        ($command:expr, $context:expr, $expected_code:expr) => {
            smtp_write!($command);
            smtp_read!($context, $expected_code);
        };
    }

    // Read initial greeting
    smtp_read!("initial greeting", "220");

    // Greet (Using HELO as we don't want to deal with extended SMTP anyway.)
    smtp_cmd!(b"HELO localhost\r\n", "HELO", "250");

    // MAIL FROM
    smtp_cmd!(
        format!("MAIL FROM:<{}>\r\n", envelope.mail_from).as_bytes(),
        "MAIL FROM",
        "250"
    );

    // RCPT TO
    for rcpt in &envelope.rcpt_to {
        smtp_cmd!(
            format!("RCPT TO:<{}>\r\n", rcpt).as_bytes(),
            "RCPT TO",
            "250"
        );
    }

    // DATA
    smtp_cmd!(b"DATA\r\n", "DATA", "354");
    smtp_write!(&envelope.data);
    smtp_write!(b".\r\n");
    smtp_read!("end of DATA", "250");

    Ok(())
}
