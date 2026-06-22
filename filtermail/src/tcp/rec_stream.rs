//! [`TcpStreamTrait`] implementation that records communication.
//!
//! Used for snapshot testing.

use super::{TcpConnect, TcpStreamTrait};
use async_trait::async_trait;
use std::net::SocketAddr;
use std::pin::Pin;
use std::task::{Context, Poll};
use tokio::io::{AsyncRead, AsyncWrite, ReadBuf};
use tokio::net::{TcpStream, ToSocketAddrs};
use tokio::sync::mpsc::Sender;

/// A stream that behaves similarly to [`TcpStream`],
/// but additionally records the whole conversation to internal buffer,
/// and sends it over [`Sender`] when dropped.
pub struct RecTcpStream {
    tx: Sender<String>,
    inner: TcpStream,
    rec_buffer: String,
    // read/write arrows
    arrows: (char, char),
}

impl RecTcpStream {
    /// Creates a new [`RecTcpStream`].
    ///
    /// Recorded conversation will be sent over `tx`.
    ///
    /// Setting `is_server` to `true`, will invert read/write arrow characters,
    /// so that they correctly used for `> client command` and `< server response`.
    pub fn new(stream: TcpStream, tx: Sender<String>, is_server: bool) -> Self {
        Self {
            tx,
            inner: stream,
            rec_buffer: String::new(),
            arrows: match is_server {
                true => ('>', '<'),
                false => ('<', '>'),
            },
        }
    }
}

impl AsyncWrite for RecTcpStream {
    fn poll_write(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buf: &[u8],
    ) -> Poll<std::io::Result<usize>> {
        let mut_self = self.get_mut();
        let inner_result = Pin::new(&mut mut_self.inner).poll_write(cx, buf);
        if inner_result.is_pending() {
            return inner_result;
        }

        if !buf.is_empty() {
            let mut data = String::from_utf8_lossy(buf).to_string();
            data = format!("{} {data}", mut_self.arrows.1);
            mut_self.rec_buffer.push_str(&data);
        }

        inner_result
    }

    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<std::io::Result<()>> {
        Pin::new(&mut self.get_mut().inner).poll_flush(cx)
    }

    fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<std::io::Result<()>> {
        Pin::new(&mut self.get_mut().inner).poll_shutdown(cx)
    }
}

impl AsyncRead for RecTcpStream {
    fn poll_read(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buf: &mut ReadBuf<'_>,
    ) -> Poll<std::io::Result<()>> {
        let mut_self = self.get_mut();
        let inner_result = Pin::new(&mut mut_self.inner).poll_read(cx, buf);
        if inner_result.is_pending() {
            return inner_result;
        }

        let filled = buf.filled();
        if !filled.is_empty() {
            let mut data = String::from_utf8_lossy(filled).to_string();
            data = format!("{} {data}", mut_self.arrows.0);
            mut_self.rec_buffer.push_str(&data);
        }

        inner_result
    }
}

impl Drop for RecTcpStream {
    fn drop(&mut self) {
        let tx = self.tx.clone();
        let rec_buffer = self.rec_buffer.clone();
        tokio::spawn(async move { tx.send(rec_buffer).await.unwrap() });
    }
}

impl TcpStreamTrait for RecTcpStream {
    fn peer_addr(&self) -> std::io::Result<SocketAddr> {
        self.inner.peer_addr()
    }

    fn set_nodelay(&self, nodelay: bool) -> std::io::Result<()> {
        self.inner.set_nodelay(nodelay)
    }
}

#[async_trait]
impl TcpConnect for RecTcpStream {
    type ConnectionContext = Sender<String>;

    async fn connect<A: ToSocketAddrs + Send>(
        addr: A,
        tx: Sender<String>,
    ) -> std::io::Result<Self> {
        let inner = TcpStream::connect(addr).await?;
        Ok(Self::new(inner, tx, false))
    }
}
