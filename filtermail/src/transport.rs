mod https_client;
mod worker;

use crate::config::Config;
use crate::smtp_responses::{LOCAL_ERROR_451, WORKER_BUSY_421};
use crate::smtp_server::{SmtpHandler, Transaction};
use crate::utils::AddressDomain;
use async_trait::async_trait;
use std::collections::BTreeMap;
use std::str::FromStr;
use tokio::sync::mpsc::OwnedPermit;
use tokio::task::JoinSet;
use worker::{WorkerMessage, WorkerPool};

pub const HEADER_MAIL_FROM: &str = "X-MAIL-FROM";
pub const HEADER_RCPT_TO: &str = "X-MAIL-TO";

pub struct TransportHandler {
    workers: WorkerPool,
}

impl TransportHandler {
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
impl SmtpHandler for TransportHandler {
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

        log::trace!(
            "Trying to acquire a permit for {} worker...",
            domain.as_ref()
        );
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
    use rstest::{fixture, rstest};
    use testresult::TestResult;

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
        let transport_handler = TransportHandler::with_queue_size(Config::default(), 1)?;
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
}
