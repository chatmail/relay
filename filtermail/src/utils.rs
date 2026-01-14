use mailparse::MailAddr;
use std::error::Error;

/// Extracts the first email address found in SMTP command or email header.
///
/// Return `None` if parsing fails.
///
/// Returns the first address if multiple are present.
pub fn extract_address(input: &str) -> Option<String> {
    // TODO: at this point it's probably simpler to use regex ;p
    let input_lower = input.to_lowercase();
    let mut trimmed = input_lower
        .trim_start_matches("mail from:")
        .trim_start_matches("rcpt to:");
    trimmed = trimmed
        .split_once("=")
        .map(|(address_raw, _)| {
            address_raw
                .rsplit_once(' ')
                .map(|(addr, _)| addr)
                .unwrap_or(address_raw)
                .trim()
        })
        .unwrap_or(trimmed);

    mailparse::addrparse(trimmed)
        .ok()
        .and_then(|addr| match addr.first() {
            Some(MailAddr::Single(single)) => Some(single.addr.clone()),
            Some(MailAddr::Group(group)) => group.addrs.first().map(|single| single.addr.clone()),
            None => None,
        })
}

/// Formats SMTP error to be able to send it back to postfix.
pub fn format_smtp_error(error: lettre::transport::smtp::Error) -> String {
    if let Some(code) = error.status() {
        format!(
            "{} {}",
            code,
            error
                .source()
                .map(ToString::to_string)
                .unwrap_or("Unknown error".to_string())
        )
    } else {
        // Default to 451, most probably means some internal service error (e.g. milter)
        format!(
            "451 {}",
            error
                .source()
                .map(ToString::to_string)
                .unwrap_or("Unknown error".to_string())
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rstest::*;

    #[rstest]
    #[case("MAIL FROM:<t1@example.org>", Some("t1@example.org".to_string()))]
    #[case("MAIL FROM:<t2@example.org> SOMETHING=SOMETHING OTHER=OTHER", Some("t2@example.org".to_string()))]
    #[case("RCPT TO:<t3@example.org>", Some("t3@example.org".to_string()))]
    #[case("mail from:<t4@example.org>", Some("t4@example.org".to_string()))]
    #[case("Foo Bar <t5@example.org>", Some("t5@example.org".to_string()))]
    #[case("t6@example.org", Some("t6@example.org".to_string()))]
    fn test_extract_address(#[case] input: &str, #[case] expected: Option<String>) {
        let result = extract_address(input);
        assert_eq!(result, expected)
    }
}
