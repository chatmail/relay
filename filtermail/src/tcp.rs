//! TCP related code.

use async_trait::async_trait;
use tokio::io::{AsyncRead, AsyncWrite};
use tokio::net::{TcpStream, ToSocketAddrs};

#[cfg(test)]
pub mod rec_stream;

/// Abstraction over [`TcpStream`] allowing e.g. mocking it.
pub trait TcpStreamTrait: AsyncRead + AsyncWrite + Unpin + Send + Sync + Sized + 'static {
    /// Returns the remote address that this stream is connected to.
    fn peer_addr(&self) -> std::io::Result<std::net::SocketAddr>;

    /// Sets the value of the `TCP_NODELAY` option on this socket.
    fn set_nodelay(&self, nodelay: bool) -> std::io::Result<()>;
}

/// Trait adding a `connect` method similar to [`TcpStream::connect`],
/// that allows passing additional context when creating the stream.
#[async_trait]
pub trait TcpConnect: TcpStreamTrait {
    /// Type of additional context passed to [`TcpConnect::connect`].
    type ConnectionContext: Send + Sync + Clone + 'static;

    /// Opens a TCP connection to a remote host.
    async fn connect<A: ToSocketAddrs + Send>(
        addr: A,
        context: Self::ConnectionContext,
    ) -> std::io::Result<Self>;
}

impl TcpStreamTrait for TcpStream {
    /// Returns the remote address that this stream is connected to.
    ///
    /// Delegates to [`TcpStream::peer_addr`].
    fn peer_addr(&self) -> std::io::Result<std::net::SocketAddr> {
        TcpStream::peer_addr(self)
    }

    /// Sets the value of the `TCP_NODELAY` option on this socket.
    ///
    /// Delegates to [`TcpStream::set_nodelay`].
    fn set_nodelay(&self, nodelay: bool) -> std::io::Result<()> {
        TcpStream::set_nodelay(self, nodelay)
    }
}

#[async_trait]
impl TcpConnect for TcpStream {
    type ConnectionContext = ();

    /// Opens a TCP connection to a remote host.
    ///
    /// Delegates to [`TcpStream::connect`].
    async fn connect<A: ToSocketAddrs + Send>(addr: A, _: ()) -> std::io::Result<Self> {
        TcpStream::connect(addr).await
    }
}
