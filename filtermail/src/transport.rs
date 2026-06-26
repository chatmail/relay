mod https_client;
mod worker;

use crate::config::Config;
use crate::smtp_responses::{LOCAL_ERROR_451, WORKER_BUSY_421};
use crate::smtp_server::{SmtpHandler, Transaction};
use crate::tcp::{TcpConnect, TcpStreamTrait};
use crate::utils::AddressDomain;
use async_trait::async_trait;
use std::collections::BTreeMap;
use std::str::FromStr;
use tokio::sync::mpsc::OwnedPermit;
use tokio::task::JoinSet;
use worker::{WorkerMessage, WorkerPool};

pub const HEADER_MAIL_FROM: &str = "X-MAIL-FROM";
pub const HEADER_RCPT_TO: &str = "X-MAIL-TO";

pub struct TransportHandler<S: TcpConnect> {
    workers: WorkerPool<S>,
}

impl<S> TransportHandler<S>
where
    S: TcpStreamTrait + TcpConnect,
    S::ConnectionContext: Default,
{
    /// Creates a new [`TransportHandler`].
    pub fn new(config: Config) -> Result<Self, crate::error::Error> {
        let workers = WorkerPool::new(config)?;

        Ok(Self { workers })
    }

    /// Same as [`Self::new`], but lets you set worker queue size.
    ///
    /// Only used for tests.
    #[cfg(test)]
    pub fn with_queue_size(config: Config, queue_size: usize) -> Result<Self, crate::error::Error> {
        let workers = WorkerPool::with_queue_size(config, queue_size)?;

        Ok(Self { workers })
    }
}

#[derive(Debug, Default)]
pub struct TransactionState {
    permits: BTreeMap<AddressDomain, OwnedPermit<WorkerMessage>>,
}

#[async_trait]
impl<S> SmtpHandler for TransportHandler<S>
where
    S: TcpStreamTrait + TcpConnect,
    S::ConnectionContext: Default,
{
    type State = TransactionState;

    fn handle_rcpt_to(
        &self,
        address: &str,
        transaction: &mut Transaction<Self::State>,
    ) -> Result<(), String> {
        let domain = AddressDomain::from_str(address).map_err(|e| e.smtp_response())?;

        if transaction.state.permits.contains_key(&domain) {
            // We already acquired a permit for this domain
            return Ok(());
        }

        log::trace!("Trying to acquire a permit for {domain} worker...",);
        if let Some(permit) = self.workers.get_permit(&domain) {
            transaction.state.permits.insert(domain, permit);
        }

        Ok(())
    }

    fn handle_data_start(&self, transaction: &Transaction<Self::State>) -> Result<(), String> {
        // We want to prevent needlessly sending data from postfix to filtermail,
        // so we fail here if we didn't get any permit.
        //
        // Examplary scenario:
        // Consider destinations A and B, where A is unavailable.
        // We are sending a message to a group of 1@A, 2@A, 1@B, 2@B.
        // After handle_rcpt_to on every recipient, we end up with a permit for domain B (A fails).
        // handle_data_start passes and mail data is transmitted to filtermail.
        // Delivery to B is performed; 1@B and 2@B receive message and a message to 1@A and 2@A
        // is deferred.
        // After some time the message is retried, now we only try to acquire permit for A,
        // but fail -> empty `transaction.state.permits`
        // handle_data_start fails and mail data is not sent to filtermail.
        // This greatly reduces RAM usage, as unavailable destination can cause large numbers of
        // deferred mails to be constantly retried.

        if transaction.state.permits.is_empty() {
            return Err(WORKER_BUSY_421.to_string());
        }

        Ok(())
    }

    /// Handles the DATA command and returns LMTP responses as single string.
    ///
    /// Never returns an error, as LMTP response is composite.
    async fn handle_data_dot(
        &self,
        transaction: &mut Transaction<Self::State>,
    ) -> Result<String, String> {
        let mut domain_rcpts_map = BTreeMap::new();

        for rcpt in &transaction.envelope.rcpt_to {
            let domain = AddressDomain::from_str(rcpt)
                // Currently we cancel all transactions if any recipient address is invalid.
                .map_err(|e| e.lmtp_response(transaction.envelope.rcpt_to.len()))?;
            domain_rcpts_map
                .entry(domain)
                .or_insert_with(Vec::new)
                .push(rcpt.to_string());
        }

        // one transaction per domain
        let mut transactions = JoinSet::new();
        let mut task_id_domain_map = BTreeMap::new();

        for (rcpt_domain, rcpts) in &domain_rcpts_map {
            let domain_envelope = {
                let mut envelope = transaction.envelope.clone();
                envelope.rcpt_to = rcpts.clone();
                envelope
            };
            let receiver_task_id =
                if let Some(permit) = transaction.state.permits.remove(rcpt_domain) {
                    let (message, receiver) = WorkerMessage::new(domain_envelope);
                    permit.send(message);
                    // todo: receiver timeout?
                    transactions.spawn(receiver).id()
                } else {
                    transactions
                        .spawn(async move { Ok(Err(WORKER_BUSY_421.to_string())) })
                        .id()
                };
            task_id_domain_map.insert(receiver_task_id, rcpt_domain);
        }

        let mut rcpt_response_map = BTreeMap::new();
        while let Some(result) = transactions.join_next_with_id().await {
            let domain = match &result {
                Ok((id, _)) => task_id_domain_map.remove(id),
                Err(e) => task_id_domain_map.remove(&e.id()),
            };

            let smtp_response = match result {
                Ok((_, Ok(Ok(resp)))) | Ok((_, Ok(Err(resp)))) => resp,
                Ok((_, Err(e))) => {
                    log::error!(
                        "Worker task failed while delivering to {}: {e}",
                        domain.map(AsRef::as_ref).unwrap_or("<unknown>")
                    );
                    LOCAL_ERROR_451.to_string()
                }
                Err(e) => {
                    log::error!(
                        "Failed to join task while delivering to {}: {e}",
                        domain.map(AsRef::as_ref).unwrap_or("<unknown>")
                    );
                    LOCAL_ERROR_451.to_string()
                }
            };

            if let Some(domain) = domain
                && let Some(rcpts) = domain_rcpts_map.get(domain)
            {
                for rcpt in rcpts {
                    rcpt_response_map.insert(rcpt, smtp_response.clone());
                }
            }
        }

        // compose lmtp response...
        let ordered_responses: Vec<String> = transaction
            .envelope
            .rcpt_to
            .iter()
            .map(|rcpt| {
                rcpt_response_map
                    .remove(rcpt)
                    .unwrap_or_else(|| LOCAL_ERROR_451.to_string())
            })
            .collect();

        Ok(ordered_responses.join("\r\n"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::smtp_client::SmtpConnectionPool;
    use crate::smtp_server::{Envelope, MockHandler, run_smtp_server};
    use crate::tcp::rec_stream::RecTcpStream;
    use rstest::{fixture, rstest};
    use serial_test::serial;
    use std::sync::Arc;
    use std::time::Duration;
    use testresult::TestResult;
    use tokio::net::{TcpSocket, TcpStream};
    use tokio::sync::mpsc::Receiver;

    const FILTERMAIL_IP: &str = "127.0.0.1";
    const FILTERMAIL_PORT: u16 = 10083;
    const FILTERMAIL_ADDR: (&str, u16) = (FILTERMAIL_IP, FILTERMAIL_PORT);

    /// Spawns a mockup SMTP server that accepts anything on `localhost:10025`.
    ///
    /// Returns a receiver that receives records of SMTP conversations.
    fn spawn_mock_mta() -> TestResult<Receiver<String>> {
        let socket = TcpSocket::new_v4()?;
        socket.set_nodelay(true)?;
        socket.set_reuseport(true)?;
        socket.bind("127.0.0.1:10025".parse()?)?;
        let remote_listener = socket.listen(8)?;
        let (tx, rx) = tokio::sync::mpsc::channel(128);
        tokio::spawn(async move {
            while let Ok((stream, _)) = remote_listener.accept().await {
                let tx_clone = tx.clone();
                let rec_stream = RecTcpStream::new(stream, tx_clone, true);
                tokio::spawn(async move {
                    crate::smtp_server::handle_connection(
                        rec_stream,
                        Arc::new(MockHandler),
                        9999, // arbitrary
                        true,
                    )
                    .await
                    .unwrap();
                });
            }
        });
        Ok(rx)
    }

    /// Spawns filtermail-transport.
    ///
    /// Returns a pointer to the underlying handler.
    fn spawn_filtermail_transport() -> TestResult<Arc<TransportHandler<TcpStream>>> {
        let config = Config::default();
        let transport = Arc::new(TransportHandler::with_queue_size(config.clone(), 1)?);
        tokio::spawn(run_smtp_server(
            &FILTERMAIL_ADDR,
            transport.clone(),
            config.max_message_size,
        ));
        Ok(transport)
    }

    /// Sends envelope over LMTP.
    ///
    /// Returns a recorded LMTP conversation.
    ///
    /// Does not fail on negative response.
    async fn lmtp_send(envelope: &Envelope) -> TestResult<String> {
        let (tx, mut rx) = tokio::sync::mpsc::channel(128);
        let client_config = crate::smtp_client::ClientConfig {
            client_hostname: "postfix",
            tls_config: None,
            lmtp: true,
        };
        let _ = crate::smtp_client::send(
            FILTERMAIL_IP,
            FILTERMAIL_PORT,
            envelope,
            client_config,
            Arc::new(crate::utils::build_resolver()?),
            SmtpConnectionPool::<RecTcpStream>::new(tx),
        )
        .await;

        let record = rx.recv().await.unwrap();

        Ok(record)
    }

    #[fixture]
    fn addrs1() -> Vec<String> {
        let mut vec = Vec::new();
        for idx in 0..5 {
            vec.push(format!("{idx}@one.example.org"))
        }
        vec
    }

    #[fixture]
    fn addrs2() -> Vec<String> {
        let mut vec = Vec::new();
        for idx in 0..5 {
            vec.push(format!("{idx}@two.example.org"))
        }
        vec
    }

    #[rstest]
    #[tokio::test]
    async fn test_rcpt_to_and_start_data(addrs1: Vec<String>, addrs2: Vec<String>) -> TestResult {
        let transport_handler =
            TransportHandler::<TcpStream>::with_queue_size(Config::default(), 1)?;
        let domain1 = AddressDomain::from_str(addrs1.first().unwrap())?;
        let domain2 = AddressDomain::from_str(addrs2.first().unwrap())?;

        {
            let mut trans_1 = Transaction::default();
            let mut trans_2 = Transaction::default();
            let mut trans_3 = Transaction::default();

            transport_handler.handle_rcpt_to(addrs1.first().unwrap(), &mut trans_1)?;
            assert!(trans_1.state.permits.contains_key(&domain1));

            // Within one transaction, we only use one worker permit, so queue_size=1 is enough.
            transport_handler.handle_rcpt_to(addrs1.get(1).unwrap(), &mut trans_1)?;
            assert!(trans_1.state.permits.contains_key(&domain1));

            // However, a second transaction with the same domain won't get a permit.
            transport_handler.handle_rcpt_to(addrs1.get(2).unwrap(), &mut trans_2)?;
            assert!(!trans_2.state.permits.contains_key(&domain1));

            // Different domain will work though, as it uses a separate worker, with its own queue.
            transport_handler.handle_rcpt_to(addrs2.first().unwrap(), &mut trans_2)?;
            assert!(trans_2.state.permits.contains_key(&domain2));

            // Third transaction won't get any permits.
            transport_handler.handle_rcpt_to(addrs1.get(3).unwrap(), &mut trans_3)?;
            transport_handler.handle_rcpt_to(addrs2.get(2).unwrap(), &mut trans_3)?;
            assert!(!trans_3.state.permits.contains_key(&domain1));
            assert!(!trans_3.state.permits.contains_key(&domain2));

            // all permits granted -> accept DATA command
            assert_eq!(transport_handler.handle_data_start(&trans_1), Ok(()));

            // some permits granted -> accept DATA command
            assert_eq!(transport_handler.handle_data_start(&trans_2), Ok(()));

            // no permits granted -> reject
            assert!(transport_handler.handle_data_start(&trans_3).is_err());
        }

        // Transactions (and owned by them permits) going out of scope frees the queues.
        let mut trans_4 = Transaction::default();
        transport_handler.handle_rcpt_to(addrs1.first().unwrap(), &mut trans_4)?;
        transport_handler.handle_rcpt_to(addrs2.first().unwrap(), &mut trans_4)?;
        assert!(trans_4.state.permits.contains_key(&domain1));
        assert!(trans_4.state.permits.contains_key(&domain2));

        Ok(())
    }

    #[rstest]
    #[serial]
    #[tokio::test]
    async fn test_smtp_send_mail() -> TestResult {
        let mut remote_mta = spawn_mock_mta()?;
        spawn_filtermail_transport()?;

        let envelope = Envelope {
            mail_from: "sender@here".to_string(),
            rcpt_to: vec![
                // Taking advantage of the fact that localhost and [127.0.0.1] are recognized as
                // different destinations.
                "a1@localhost".to_string(),
                "a2@localhost".to_string(),
                "b1@[127.0.0.1]".to_string(),
                "b2@[127.0.0.1]".to_string(),
            ],
            data: "message\r\n".as_bytes().to_vec(),
        };

        let record = lmtp_send(&envelope).await?;

        let mut remote_records = [
            remote_mta.recv().await.unwrap(),
            remote_mta.recv().await.unwrap(),
        ];
        remote_records.sort_by_key(|s| s.contains("b1@[127.0.0.1]"));
        tokio::time::sleep(Duration::from_secs(1)).await;
        assert!(remote_mta.is_empty());

        insta::assert_snapshot!(format!(
            "[postfix -> filtermail-transport]\r\n{record}\r\n\
            [filtermail-transport -> destination A]\r\n{}\r\n\
            [filtermail-transport -> destination B]\r\n{}",
            remote_records[0], remote_records[1]
        ));

        Ok(())
    }

    #[rstest]
    #[serial]
    #[tokio::test]
    async fn test_smtp_send_mail_defer() -> TestResult {
        let mut remote_mta = spawn_mock_mta()?;
        let transport = spawn_filtermail_transport()?;

        let mut envelope = Envelope {
            mail_from: "sender@here".to_string(),
            rcpt_to: vec!["a1@localhost".to_string(), "b1@[127.0.0.1]".to_string()],
            data: "message\r\n".as_bytes().to_vec(),
        };

        let (record_postfix_1, record_filtermail_1) = {
            // simulate full queue on [127.0.0.1] worker
            let _permit = transport
                .workers
                .get_permit(&AddressDomain::Literal("127.0.0.1".to_string()));

            let record_postfix = lmtp_send(&envelope).await?;

            let record_filtermail = remote_mta.recv().await.unwrap();
            tokio::time::sleep(Duration::from_secs(1)).await;
            assert!(remote_mta.is_empty());
            (record_postfix, record_filtermail)
        };

        // retry deferred
        envelope.rcpt_to.remove(0);
        let record_postfix_2 = lmtp_send(&envelope).await?;
        let record_filtermail_2 = remote_mta.recv().await.unwrap();
        tokio::time::sleep(Duration::from_secs(1)).await;
        assert!(remote_mta.is_empty());

        insta::assert_snapshot!(format!(
            "TRANSACTION 1\r\n\
            [postfix -> filtermail-transport]\r\n{record_postfix_1}\r\n\
            [filtermail-transport -> destination A]\r\n{record_filtermail_1}\r\n\r\n\
            TRANSACTION 2\r\n\
            [postfix -> filtermail-transport]\r\n{record_postfix_2}\r\n\
            [filtermail-transport -> destination B]\r\n{record_filtermail_2}",
        ));

        Ok(())
    }
}
