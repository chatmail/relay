//! Module for rate limiting.

use std::collections::HashMap;
use std::time::{Duration, SystemTime};

const ONE_MINUTE: Duration = Duration::from_secs(60);

/// A rate limiter tracking send timestamps per address.
#[derive(Debug, Default)]
pub struct SendRateLimiter {
    address_timestamps: HashMap<String, Vec<SystemTime>>,
}

impl SendRateLimiter {
    pub fn is_sending_allowed(&mut self, mail_from: &str, max_send_per_minute: usize) -> bool {
        self.address_timestamps.retain(|_, timestamps| {
            timestamps
                .last()
                .map(|t| t.elapsed().unwrap_or_default() <= ONE_MINUTE)
                .unwrap_or(false)
        });

        let last = self
            .address_timestamps
            .entry(mail_from.to_string())
            .or_default();
        last.retain(|&send_time| send_time.elapsed().unwrap_or_default() <= ONE_MINUTE);
        if last.len() <= max_send_per_minute {
            last.push(SystemTime::now());
            true
        } else {
            false
        }
    }
}
