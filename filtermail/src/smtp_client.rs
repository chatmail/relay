use crate::smtp_server::Envelope;
use hickory_resolver::TokioResolver;
use std::pin::Pin;
use std::sync::Arc;
use std::task::{Context, Poll};
use std::time::Duration;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufStream};
use tokio::io::{AsyncRead, AsyncWrite, ReadBuf};
use tokio::net::TcpStream;
use tokio::task::JoinSet;
use tokio_io_timeout::TimeoutStream;
use tokio_rustls::rustls::client::ClientSessionMemoryCache;

/// A [`TcpStream`] used for SMTP communication.
#[expect(clippy::large_enum_variant)]
enum SmtpStream {
    /// A plain TCP stream.
    Plain(Pin<Box<TimeoutStream<TcpStream>>>),
    /// A TLS-encrypted stream.
    Tls(tokio_rustls::TlsStream<Pin<Box<TimeoutStream<TcpStream>>>>),
}

impl SmtpStream {
    /// Creates a new plain SMTP stream from a raw TCP stream,
    /// with read and write timeouts set to 60 seconds.
    fn plain(stream: TcpStream) -> Self {
        let mut timeout_stream = TimeoutStream::new(stream);
        timeout_stream.set_write_timeout(Some(Duration::from_secs(60)));
        timeout_stream.set_read_timeout(Some(Duration::from_secs(60)));
        Self::Plain(Box::pin(timeout_stream))
    }
}

#[derive(Debug, Clone)]
pub struct TlsConfig {
    pub(crate) allow_invalid_cert: bool,
    pub(crate) session_cache: Arc<ClientSessionMemoryCache>,
}

impl AsyncWrite for SmtpStream {
    fn poll_write(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buf: &[u8],
    ) -> Poll<std::io::Result<usize>> {
        match self.get_mut() {
            SmtpStream::Plain(stream) => Pin::new(stream).poll_write(cx, buf),
            SmtpStream::Tls(stream) => Pin::new(stream).poll_write(cx, buf),
        }
    }

    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<std::io::Result<()>> {
        match self.get_mut() {
            SmtpStream::Plain(stream) => Pin::new(stream).poll_flush(cx),
            SmtpStream::Tls(stream) => Pin::new(stream).poll_flush(cx),
        }
    }

    fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<std::io::Result<()>> {
        match self.get_mut() {
            SmtpStream::Plain(stream) => Pin::new(stream).poll_shutdown(cx),
            SmtpStream::Tls(stream) => Pin::new(stream).poll_shutdown(cx),
        }
    }
}

impl AsyncRead for SmtpStream {
    fn poll_read(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buf: &mut ReadBuf<'_>,
    ) -> Poll<std::io::Result<()>> {
        match self.get_mut() {
            SmtpStream::Plain(stream) => Pin::new(stream).poll_read(cx, buf),
            SmtpStream::Tls(stream) => Pin::new(stream).poll_read(cx, buf),
        }
    }
}

/// Converts address and port to a list of socket addresses.
///
/// Performs non-blocking DNS resolution if address is a domain name,
/// or returns a single socket address if address is an IP.
async fn to_socket_addrs(
    address: &str,
    port: u16,
    dns_resolver: Arc<TokioResolver>,
) -> Result<Vec<std::net::SocketAddr>, crate::error::Error> {
    log::trace!("Resolving {address}...");
    if let Ok(ip) = address.parse() {
        Ok(vec![std::net::SocketAddr::new(ip, port)])
    } else {
        let lookup = dns_resolver.lookup_ip(address).await?;
        Ok(lookup
            .iter()
            .map(|ip| std::net::SocketAddr::new(ip, port))
            .collect())
    }
}

/// Establishes a TCP connection to the given address and port, trying all resolved IPs in parallel.
async fn establish_tcp_connection(
    address: &str,
    port: u16,
    dns_resolver: Arc<TokioResolver>,
) -> Result<TcpStream, crate::error::Error> {
    let mut set: JoinSet<tokio::io::Result<TcpStream>> = JoinSet::new();

    let socket_addrs = to_socket_addrs(address, port, dns_resolver).await?;

    for addr in socket_addrs.clone() {
        set.spawn(async move {
            log::trace!("SMTP client: connecting to {addr}...");
            let stream =
                tokio::time::timeout(Duration::from_secs(60), TcpStream::connect(addr)).await??;
            stream.set_nodelay(true)?;
            Ok(stream)
        });
    }
    let mut stream: Option<TcpStream> = None;
    while let Some(result) = set.join_next().await {
        match result {
            Ok(Ok(s)) => {
                stream = Some(s);
                break;
            }
            Ok(Err(e)) => log::debug!("Failed to connect to socket: {e}"),
            Err(e) => log::debug!("Failed to join task: {e}"),
        }
    }

    match stream {
        Some(s) => Ok(s),
        None => Err(crate::error::Error::ConnectionFailed(
            socket_addrs.into_iter().map(|a| a.to_string()).collect(),
        )),
    }
}

/// Sends an email using an SMTP server at `smtp_addr`.
///
/// If `tls_config` is provided, the connection will be upgraded to TLS.
/// The client will fail early if the server does not support STARTTLS.
///
/// If `address` is a domain that resolves to multiple IP addresses,
/// all will be tried in parallel and the first successful connection will be used.
pub async fn send(
    address: &str,
    port: u16,
    envelope: &Envelope,
    client_hostname: &str,
    tls_config: Option<TlsConfig>,
    dns_resolver: Arc<TokioResolver>,
) -> Result<(), crate::error::Error> {
    let stream = establish_tcp_connection(address, port, dns_resolver).await?;

    log::debug!(
        "SMTP client: successfully connected to {}",
        stream.peer_addr()?
    );

    let mut buf_stream = BufStream::new(SmtpStream::plain(stream));
    let mut response = String::new();

    macro_rules! smtp_write {
        ($command: expr) => {
            log::trace!(
                "SMTP client: sending: {}",
                String::from_utf8_lossy($command)
            );
            buf_stream.write_all($command).await?;
            buf_stream.flush().await?;
        };
    }

    macro_rules! smtp_read {
        ($context:expr, $expected_code:expr) => {
            response.clear();
            let mut next_line = String::new();
            buf_stream.read_line(&mut next_line).await?;
            response.push_str(&next_line);
            while let Some(c) = next_line.as_bytes().get(3)
                && *c == b'-'
            {
                next_line.clear();
                buf_stream.read_line(&mut next_line).await?;
                response.push_str(&next_line);
            }
            log::trace!("SMTP response for {}:\n{}", $context, response);
            if !response.starts_with($expected_code) {
                return Err(crate::error::Error::MailSend {
                    context: $context.to_string(),
                    raw_smtp_answer: response.clone(),
                });
            }
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

    if tls_config.is_some() {
        smtp_cmd!(
            format!("EHLO {client_hostname}\r\n").as_bytes(),
            "EHLO",
            "250"
        );
    } else {
        smtp_cmd!(
            format!("HELO {client_hostname}\r\n").as_bytes(),
            "HELO",
            "250"
        );
    };

    // STARTTLS
    if let Some(tls_config) = tls_config {
        if !response.to_uppercase().contains("STARTTLS") {
            // TLS was requested, but server doesn't support STARTTLS.
            return Err(crate::error::Error::MailSend {
                context: "STARTTLS".to_string(),
                raw_smtp_answer: response.clone(),
            });
        }

        log::trace!("Initiating STARTTLS...");
        smtp_cmd!(b"STARTTLS\r\n", "STARTTLS", "220");

        let stream = buf_stream.into_inner();
        let raw_tcp = match stream {
            SmtpStream::Plain(s) => s,
            SmtpStream::Tls(_) => {
                unreachable!("This is the first and only place we upgrade to TLS.")
            }
        };

        let tls_stream = crate::tls::wrap_rustls(
            address,
            raw_tcp,
            tls_config.session_cache,
            tls_config.allow_invalid_cert,
        )
        .await?;

        let smtp_stream = SmtpStream::Tls(tls_stream);

        buf_stream = BufStream::new(smtp_stream);

        smtp_cmd!(
            format!("EHLO {client_hostname}\r\n").as_bytes(),
            "EHLO after STARTTLS",
            "250"
        );
    }

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
