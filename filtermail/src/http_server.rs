use crate::smtp_server::{Envelope, SmtpHandler};
use http_body_util::combinators::BoxBody;
use http_body_util::{BodyExt, Full};
use hyper::body::{Bytes, Incoming};
use hyper::service::Service;
use hyper::{Request, Response};
use hyper_util::rt::TokioIo;
use std::convert::Infallible;
use std::pin::Pin;
use std::sync::Arc;
use std::time::Duration;
use tokio::net::{TcpListener, TcpStream};

/// Runs the HTTP server on the specified address with the given handler and maximum message size.
pub async fn run_http_server<H>(
    addr: &impl tokio::net::ToSocketAddrs,
    handler: Arc<H>,
    max_size: usize,
) -> Result<(), crate::error::Error>
where
    H: SmtpHandler + 'static,
{
    let listener = TcpListener::bind(addr).await?;
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

/// Handles a single HTTP connection.
async fn handle_connection<H>(
    socket: TcpStream,
    handler: Arc<H>,
    max_size: usize,
) -> Result<(), String>
where
    H: SmtpHandler + 'static,
{
    let service = MxDelivService::new(handler, max_size);

    hyper_util::server::conn::auto::Builder::new(hyper_util::rt::TokioExecutor::new())
        .serve_connection(TokioIo::new(socket), service)
        .await
        .map_err(|e| e.to_string())?;

    Ok(())
}

struct MxDelivService<H: SmtpHandler> {
    handler: Arc<H>,
    max_size: usize,
}

impl<H: SmtpHandler> MxDelivService<H> {
    /// Creates a new [`MxDelivService`].
    fn new(handler: Arc<H>, max_size: usize) -> Self {
        Self { handler, max_size }
    }
}

impl<H: SmtpHandler + 'static> Service<Request<Incoming>> for MxDelivService<H> {
    type Response = Response<BoxBody<Bytes, Infallible>>;
    type Error = crate::error::Error;
    type Future = Pin<Box<dyn Future<Output = Result<Self::Response, Self::Error>> + Send>>;

    fn call(&self, req: Request<Incoming>) -> Self::Future {
        let handler = self.handler.clone();
        let max_size = self.max_size;

        let fut = async move {
            if req.method() != hyper::Method::POST {
                return Ok(Response::builder().status(405).body(
                    // This is client's implementation error if it happens,
                    // so we don't care about sending a proper smtp response.
                    Full::new(Bytes::from("Method Not Allowed")).boxed(),
                )?);
            }

            let mail_from = req
                .headers()
                .get(crate::transport::HEADER_MAIL_FROM)
                .and_then(|v| v.to_str().ok())
                .unwrap_or("")
                .to_string();

            match handler.handle_mail(&mail_from) {
                Ok(_) => {}
                Err(e) => {
                    return Ok(Response::builder()
                        .status(400)
                        .body(Full::new(Bytes::from(e)).boxed())?);
                }
            };

            let rcpt_to = req
                .headers()
                .get_all(crate::transport::HEADER_RCPT_TO)
                .iter()
                .filter_map(|v| v.to_str().ok())
                .map(ToString::to_string)
                .collect();

            let body_limited = http_body_util::Limited::new(req.into_body(), max_size);
            let body_bytes = match body_limited.collect().await {
                Ok(body) => body.to_bytes(),
                Err(_) => {
                    return Ok(Response::builder().status(413).body(
                        Full::new(Bytes::from("552 Message exceeds maximum size")).boxed(),
                    )?);
                }
            };

            let mut envelope = Envelope {
                origin_ip: "".to_string(),
                mail_from,
                rcpt_to,
                data: body_bytes.to_vec(),
            };

            log::debug!("(HTTP) MAIL FROM:<{}>", envelope.mail_from);
            for rcpt in &envelope.rcpt_to {
                log::debug!("(HTTP) RCPT TO:<{}>", rcpt);
            }

            log::trace!(
                "(HTTP) DATA:\n{:?}",
                String::from_utf8_lossy(&envelope.data)
            );

            match handler.handle_data(&mut envelope).await {
                Ok(response) => Ok(Response::builder()
                    .status(200)
                    .body(Full::new(Bytes::from(response)).boxed())?),
                Err(e) => Ok(Response::builder()
                    .status(400)
                    .body(Full::new(Bytes::from(e)).boxed())?),
            }
        };

        Box::pin(fut)
    }
}
