//! Message-related checks.

use crate::openpgp::check_armored_payload;
use mailparse::MailHeaderMap;

/// Check if message is a secure-join message (vc-request or vg-request)
pub fn is_securejoin(mail: &mailparse::ParsedMail) -> bool {
    // Check for secure-join header
    let secure_join = mail.headers.get_first_value("Secure-Join");
    if let Some(ref val) = secure_join {
        if val != "vc-request" && val != "vg-request" {
            return false;
        }
    } else {
        return false;
    }

    // Must be multipart
    if mail.subparts.is_empty() {
        return false;
    }

    // Must have only one part
    if mail.subparts.len() != 1 {
        return false;
    }

    let Some(part) = &mail.subparts.first() else {
        return false;
    };

    // Part must not be multipart
    if !part.subparts.is_empty() {
        return false;
    }

    // Part must be text/plain
    if part.ctype.mimetype != "text/plain" {
        return false;
    }

    // Check payload content
    let payload = match part.get_body() {
        Ok(p) => p.trim().to_lowercase(),
        Err(_) => return false,
    };

    payload == "secure-join: vc-request" || payload == "secure-join: vg-request"
}

/// Check that the message is an OpenPGP-encrypted message
///
/// MIME structure must correspond to RFC3156
pub fn check_encrypted(mail: &mailparse::ParsedMail, outgoing: bool) -> bool {
    if mail.subparts.is_empty() {
        log::debug!("check_encrypted: not multipart");
        return false;
    }
    if !mail
        .ctype
        .mimetype
        .eq_ignore_ascii_case("multipart/encrypted")
    {
        log::debug!("check_encrypted: not multipart/encrypted");
        return false;
    }
    for (part_idx, part) in mail.subparts.iter().enumerate() {
        // Each part must not be multipart
        if !part.subparts.is_empty() {
            log::debug!("check_encrypted: part of multipart/encrypted is itself multipart");
            return false;
        }

        if part_idx == 0 {
            // First part must be application/pgp-encrypted
            if !part
                .ctype
                .mimetype
                .eq_ignore_ascii_case("application/pgp-encrypted")
            {
                log::debug!(
                    "check_encrypted: first part not application/pgp-encrypted, got: {}",
                    part.ctype.mimetype
                );
                return false;
            }

            // Payload must be "Version: 1"
            let payload = match part.get_body() {
                Ok(p) => p,
                Err(_) => {
                    log::debug!("check_encrypted: failed to get body of first part");
                    return false;
                }
            };
            if payload.trim() != "Version: 1" {
                log::debug!(
                    "check_encrypted: first part payload not 'Version: 1', got {}",
                    payload.trim()
                );
                return false;
            }
        } else if part_idx == 1 {
            // Second part must be application/octet-stream
            if part.ctype.mimetype != "application/octet-stream" {
                log::debug!(
                    "check_encrypted: second part not application/octet-stream, got: {}",
                    part.ctype.mimetype
                );
                return false;
            }

            // Check the armored payload
            let payload = match part.get_body() {
                Ok(p) => p,
                Err(_) => {
                    log::debug!("check_encrypted: failed to get body of second part");
                    return false;
                }
            };
            if !check_armored_payload(&payload, outgoing) {
                log::debug!("check_encrypted: armored payload check failed");
                return false;
            }
        } else {
            log::debug!("check_encrypted: more than two parts found");
            return false;
        }
    }

    true
}

/// Check if recipient matches a passthrough pattern
pub fn recipient_matches_passthrough(recipient: &str, passthrough_recipients: &[String]) -> bool {
    for addr in passthrough_recipients {
        if recipient == addr {
            return true;
        }
        if addr.starts_with('@') && recipient.ends_with(addr) {
            return true;
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;
    use mailparse::parse_mail;
    use rstest::*;
    use testresult::TestResult;

    #[fixture]
    fn passthrough_recipients() -> Vec<String> {
        vec!["pass@example.org".to_string(), "@example.com".to_string()]
    }

    #[rstest]
    #[case::asm("test_data/asm.eml", false)]
    #[case::encrypted("test_data/encrypted.eml", false)]
    #[case::fake_encrypted("test_data/fake-encrypted.eml", false)]
    #[case::literal("test_data/literal.eml", false)]
    #[case::mailer_daemon("test_data/mailer-daemon.eml", false)]
    #[case::mdn("test_data/mdn.eml", false)]
    #[case::plain("test_data/plain.eml", false)]
    #[case::securejoin_vc("test_data/securejoin-vc.eml", true)]
    #[case::securejoin_vc_fake("test_data/securejoin-vc-fake.eml", false)]
    fn test_is_securejoin(#[case] file: &str, #[case] expected: bool) -> TestResult {
        let raw_email = std::fs::read_to_string(file)?;
        let parsed = parse_mail(raw_email.as_bytes())?;
        assert_eq!(is_securejoin(&parsed), expected);
        Ok(())
    }

    #[rstest]
    #[case::asm("test_data/asm.eml", false)]
    #[case::encrypted("test_data/encrypted.eml", true)]
    #[case::fake_encrypted("test_data/fake-encrypted.eml", false)]
    #[case::literal("test_data/literal.eml", false)]
    #[case::mailer_daemon("test_data/mailer-daemon.eml", false)]
    #[case::mdn("test_data/mdn.eml", false)]
    #[case::plain("test_data/plain.eml", false)]
    #[case::securejoin_vc("test_data/securejoin-vc.eml", false)]
    #[case::securejoin_vc_fake("test_data/securejoin-vc-fake.eml", false)]
    fn test_check_encrypted(#[case] file: &str, #[case] expected: bool) -> TestResult {
        let raw_email = std::fs::read_to_string(file)?;
        let parsed = parse_mail(raw_email.as_bytes())?;
        assert_eq!(check_encrypted(&parsed, false), expected);
        Ok(())
    }

    #[rstest]
    #[case("pass@example.org", true)]
    #[case("other@example.org", false)]
    #[case("anything@example.com", true)]
    #[case("anything@sub.example.com", false)]
    fn test_recipient_matches_passthrough(
        #[case] recipient: &str,
        #[case] expected: bool,
        passthrough_recipients: Vec<String>,
    ) {
        let result = recipient_matches_passthrough(recipient, &passthrough_recipients);
        assert_eq!(result, expected);
    }
}
