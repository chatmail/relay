//! Configuration file handling for filtermail.

use serde::{Deserialize, Deserializer};
use std::path::{Path, PathBuf};

/// Chatmail configuration subset used by filtermail.
#[derive(Debug, Clone, Deserialize)]
pub struct Config {
    #[serde(default = "Config::default_filtermail_smtp_port")]
    pub filtermail_smtp_port: u16,
    #[serde(default = "Config::default_filtermail_smtp_port_incoming")]
    pub filtermail_smtp_port_incoming: u16,
    #[serde(default = "Config::default_postfix_reinject_port")]
    pub postfix_reinject_port: u16,
    #[serde(default = "Config::default_postfix_reinject_port_incoming")]
    pub postfix_reinject_port_incoming: u16,
    #[serde(default = "Config::default_max_message_size")]
    pub max_message_size: usize,
    pub max_user_send_per_minute: usize,
    #[serde(default, deserialize_with = "deserialize_sequence")]
    pub passthrough_senders: Vec<String>,
    #[serde(default, deserialize_with = "deserialize_sequence")]
    pub passthrough_recipients: Vec<String>,
    mail_domain: String,
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

    /// Check if not encrypted mail is allowed for the given address.
    pub fn is_cleartext_ok(&self, addr: &str) -> bool {
        if addr.is_empty() || !addr.contains('@') || addr.contains('/') {
            return false;
        }

        let mut enforce_e2ee = self.mailboxes_dir();
        enforce_e2ee.push(addr);
        enforce_e2ee.push("enforceE2EEincoming");

        !enforce_e2ee.exists()
    }

    // Following are needed since serde does not support default literals.

    const fn default_filtermail_smtp_port() -> u16 {
        10080
    }
    const fn default_filtermail_smtp_port_incoming() -> u16 {
        10081
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
}
