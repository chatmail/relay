use hickory_resolver::{TokioResolver, proto::dnssec::TrustAnchors};
use mailparse::MailAddr;
use std::path::PathBuf;
use std::str::FromStr;
use std::sync::Arc;
use std::time::Duration;

/// Extracts the first email address found in SMTP command or email header.
///
/// Return `None` if parsing fails.
///
/// Returns the first address if multiple are present.
pub fn extract_address(input: &str) -> Option<String> {
    let input_lower = input.to_lowercase();
    let mut trimmed = input_lower
        .trim_start_matches("mail from:")
        .trim_start_matches("rcpt to:");

    let addr_end = trimmed.find('>').unwrap_or(trimmed.len() - 1);
    trimmed = trimmed
        .split_at_checked(addr_end + 1)
        .map(|(address_raw, _)| address_raw)
        .unwrap_or(trimmed);

    mailparse::addrparse(trimmed)
        .ok()
        .and_then(|addr| match addr.first() {
            Some(MailAddr::Single(single)) => Some(single.addr.clone()),
            Some(MailAddr::Group(group)) => group.addrs.first().map(|single| single.addr.clone()),
            None => None,
        })
}

/// Domain part of an email address, either a domain-literal (IP address in square brackets with
/// optional protocol prefix) or a regular domain name.
#[derive(Debug, PartialEq, Eq, Hash, Clone, PartialOrd, Ord)]
pub enum AddressDomain {
    /// Domain literal, e.g.
    /// - `192.0.2.0` in `test@[192.0.2.0]`,
    /// - `2001:db8::1` in `test@[IPv6:2001:db8::1]`.
    Literal(String),
    /// Regular domain name, e.g. `example.org` in `test@example.org`.
    Name(String),
}

impl FromStr for AddressDomain {
    type Err = crate::error::Error;

    /// Extracts the domain part from an email address and returns it as an [`AddressDomain`].
    ///
    /// Returns an [`Error`] if `address` is not a valid email address.
    ///
    /// [`Error`]: crate::error::Error
    fn from_str(address: &str) -> Result<Self, Self::Err> {
        let parts: Vec<&str> = address.split('@').collect();
        if parts.len() == 2
            && let Some(domain) = parts.get(1)
        {
            // domain literals
            if domain.starts_with('[') && domain.ends_with(']') {
                let mut address_trimmed = domain
                    .get(1..domain.len() - 1)
                    .unwrap_or(domain)
                    .to_lowercase();

                address_trimmed = address_trimmed
                    .strip_prefix("ipv6:")
                    .unwrap_or(&address_trimmed)
                    .to_string();

                return Ok(AddressDomain::Literal(address_trimmed.to_string()));
            }
            Ok(AddressDomain::Name(domain.to_string()))
        } else {
            Err(crate::error::Error::InvalidEmailAddress(
                address.to_string(),
            ))
        }
    }
}

impl AsRef<str> for AddressDomain {
    fn as_ref(&self) -> &str {
        match self {
            AddressDomain::Literal(literal) => literal.as_ref(),
            AddressDomain::Name(name) => name.as_ref(),
        }
    }
}

/// Logs email to `/tmp/filtermail-rejected/<reason>/<timestamp>.eml`
/// and returns the file path.
///
/// Returns [`crate::error::Error`] on IO error.
pub async fn log_eml(reason: &str, data: &[u8]) -> Result<PathBuf, crate::error::Error> {
    let timestamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    let filename = format!("{timestamp}.eml");
    let mut path = PathBuf::from(format!("/tmp/filtermail-rejected/{reason}"));
    tokio::fs::create_dir_all(&path).await?;
    path.push(filename);
    tokio::fs::write(&path, data).await?;
    Ok(path)
}

/// Creates a DNS resolver with DNSSEC enabled and system configuration (resolv.conf).
pub fn build_resolver() -> Result<TokioResolver, crate::error::Error> {
    let mut builder = TokioResolver::builder_tokio()?
        // https://github.com/hickory-dns/hickory-dns/issues/3519
        .with_trust_anchor(Arc::new(TrustAnchors::default()));

    // disable negative caching to prevent possible federation problems
    builder.options_mut().negative_max_ttl = Some(Duration::ZERO);

    let dns_resolver = builder.build()?;

    assert!(
        dns_resolver.options().validate,
        "incorrect resolver config: DNSSEC disabled; exiting"
    );

    Ok(dns_resolver)
}

#[cfg(test)]
mod tests {
    use super::*;
    use rstest::*;

    #[rstest]
    #[case("MAIL FROM:<t1@example.org>", Some("t1@example.org".to_string()))]
    #[case("MAIL FROM:<t2@example.org> SOMETHING=SOMETHING OTHER=OTHER", Some("t2@example.org".to_string()))]
    #[case("MAIL FROM:<SRS1=HHH=example.com==HHH=TT=example.org=alice@example.net> abc=def", Some("srs1=hhh=example.com==hhh=tt=example.org=alice@example.net".to_string()))]
    #[case("MAIL FROM:<abc+alice@example.net> abc=def", Some("abc+alice@example.net".to_string()))]
    #[case("RCPT TO:<t3@example.org>", Some("t3@example.org".to_string()))]
    #[case("mail from:<t4@example.org>", Some("t4@example.org".to_string()))]
    #[case("Foo Bar <t5@example.org>", Some("t5@example.org".to_string()))]
    #[case("t6@example.org", Some("t6@example.org".to_string()))]
    #[case("t7@[192.0.2.0]", Some("t7@[192.0.2.0]".to_string()))]
    #[case("<t7@[192.0.2.0]>", Some("t7@[192.0.2.0]".to_string()))]
    // This is a bug in mailparse, it refuses to parse IPv6 without "<>" around.
    // https://github.com/staktrace/mailparse/issues/137
    #[case("t8@[IPv6:2001:db8::1]", None)]
    #[case("<t8@[IPv6:2001:db8::1]>", Some("t8@[ipv6:2001:db8::1]".to_string()))]
    fn test_extract_address(#[case] input: &str, #[case] expected: Option<String>) {
        let result = extract_address(input);
        assert_eq!(result, expected)
    }

    #[rstest]
    #[case("t1@example.org", Some(AddressDomain::Name("example.org".to_string())))]
    #[case("SRS1=HHH=example.com==HHH=TT=example.org=alice@example.net", Some(AddressDomain::Name("example.net".to_string())))]
    #[case("t7@[192.0.2.0]", Some(AddressDomain::Literal("192.0.2.0".to_string())))]
    #[case("t8@[IPv6:2001:db8::1]", Some(AddressDomain::Literal("2001:db8::1".to_string())))]
    #[case("invalid", None)]
    #[case("invalid@address@com", None)]
    fn test_get_domain_from_address(#[case] input: &str, #[case] expected: Option<AddressDomain>) {
        let result = AddressDomain::from_str(input).ok();
        assert_eq!(result, expected);
    }
}
