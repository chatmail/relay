use mailparse::MailAddr;

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
    fn test_extract_address(#[case] input: &str, #[case] expected: Option<String>) {
        let result = extract_address(input);
        assert_eq!(result, expected)
    }
}
