//! Configuration file handling for filtermail.

use serde::{Deserialize, Deserializer};
use std::net::IpAddr;
use std::num::NonZeroU32;
use std::path::{Path, PathBuf};

/// Chatmail configuration subset used by filtermail.
#[derive(Debug, Clone, Deserialize)]
pub struct Config {
    #[serde(default = "Config::default_filtermail_host")]
    pub filtermail_host: IpAddr,
    #[serde(default = "Config::default_filtermail_smtp_port")]
    pub filtermail_smtp_port: u16,
    #[serde(default = "Config::default_filtermail_smtp_port_incoming")]
    pub filtermail_smtp_port_incoming: u16,
    #[serde(default = "Config::default_postfix_host")]
    pub postfix_host: String,
    #[serde(default = "Config::default_postfix_reinject_port")]
    pub postfix_reinject_port: u16,
    #[serde(default = "Config::default_postfix_reinject_port_incoming")]
    pub postfix_reinject_port_incoming: u16,
    #[serde(default = "Config::default_max_message_size")]
    pub max_message_size: usize,
    #[serde(default = "Config::default_max_user_send_per_minute")]
    pub max_user_send_per_minute: NonZeroU32,
    #[serde(default = "Config::default_max_user_send_burst_size")]
    pub max_user_send_burst_size: NonZeroU32,
    #[serde(default, deserialize_with = "deserialize_sequence")]
    pub passthrough_senders: Vec<String>,
    #[serde(default, deserialize_with = "deserialize_sequence")]
    pub passthrough_recipients: Vec<String>,
    pub mail_domain: String,
    mailboxes_dir: Option<PathBuf>,
}

#[derive(Debug, Clone, Deserialize)]
struct ConfigWrapper {
    // The whole actual config is under `params` section.
    pub params: Config,
}

/// Custom deserializer to parse space-separated strings into [`Vec<String>`].
fn deserialize_sequence<'de, D>(deserializer: D) -> Result<Vec<String>, D::Error>
where
    D: Deserializer<'de>,
{
    let s: Option<String> = Deserialize::deserialize(deserializer)?;
    Ok(match s {
        Some(v) => v
            .split(' ')
            .map(|item| item.trim().to_string())
            .filter(|item| !item.is_empty())
            .collect(),
        None => Vec::new(),
    })
}

impl Config {
    /// Load configuration from a file.
    pub fn from_file(path: impl AsRef<Path>) -> Result<Self, crate::error::Error> {
        let content = std::fs::read_to_string(path)?;
        let wrapped_config: ConfigWrapper = serini::from_str(&content)?;
        Ok(wrapped_config.params)
    }

    /// Get the mailboxes directory, defaulting to `/home/vmail/mail/<mail_domain>` if not set.
    fn mailboxes_dir(&self) -> PathBuf {
        match &self.mailboxes_dir {
            Some(dir) => dir.clone(),
            None => PathBuf::from(format!("/home/vmail/mail/{}", self.mail_domain)),
        }
    }

    /// Check if a specific flag file exists for the given address.
    ///
    /// Returns `default` if the address is invalid.
    fn check_flag(&self, addr: &str, flag: &str, default: bool) -> bool {
        if addr.is_empty() || !addr.contains('@') || addr.contains('/') {
            return default;
        }

        let mut path = self.mailboxes_dir();
        path.push(addr);
        path.push(flag);

        path.exists()
    }

    /// Check if not encrypted mail is allowed for the given address.
    pub fn is_cleartext_ok(&self, addr: &str) -> bool {
        !self.check_flag(addr, "enforceE2EEincoming", true)
    }

    /// Check if the given address is disabled.
    pub fn is_disabled(&self, addr: &str) -> bool {
        self.check_flag(addr, "DISABLED", false)
    }

    // Following are needed since serde does not support default literals.

    const fn default_filtermail_host() -> IpAddr {
        IpAddr::V4(std::net::Ipv4Addr::LOCALHOST)
    }
    const fn default_filtermail_smtp_port() -> u16 {
        10080
    }
    const fn default_filtermail_smtp_port_incoming() -> u16 {
        10081
    }
    fn default_postfix_host() -> String {
        "127.0.0.1".to_owned()
    }
    const fn default_postfix_reinject_port() -> u16 {
        10025
    }
    const fn default_postfix_reinject_port_incoming() -> u16 {
        10026
    }
    const fn default_max_message_size() -> usize {
        31457280
    }
    const fn default_max_user_send_per_minute() -> NonZeroU32 {
        NonZeroU32::new(60).expect("60 != 0")
    }
    const fn default_max_user_send_burst_size() -> NonZeroU32 {
        NonZeroU32::new(10).expect("10 != 0")
    }
}

#[cfg(test)]
impl Default for Config {
    /// Creates a default configuration with example.org domain.
    ///
    /// Used for tests.
    fn default() -> Self {
        Self {
            filtermail_host: Self::default_filtermail_host(),
            filtermail_smtp_port: Self::default_filtermail_smtp_port(),
            filtermail_smtp_port_incoming: Self::default_filtermail_smtp_port_incoming(),
            postfix_host: Self::default_postfix_host(),
            postfix_reinject_port: Self::default_postfix_reinject_port(),
            postfix_reinject_port_incoming: Self::default_postfix_reinject_port_incoming(),
            max_message_size: Self::default_max_message_size(),
            max_user_send_per_minute: Self::default_max_user_send_per_minute(),
            max_user_send_burst_size: Self::default_max_user_send_burst_size(),
            passthrough_senders: Vec::new(),
            passthrough_recipients: Vec::new(),
            mail_domain: "example.org".to_string(),
            mailboxes_dir: None,
        }
    }
}
