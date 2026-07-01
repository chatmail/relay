use hickory_resolver::{TokioResolver, proto::rr::Name};
use lru::LruCache;
use std::io;
use std::num::NonZeroUsize;
use std::pin::Pin;
use std::sync::Arc;
use std::time::Duration;
use viadkim::VerificationStatus;
use viadkim::message_hash::BodyHasherStance;
use viadkim::verifier::LookupTxt;

// ~500kB when fully saturated (~420B per RDATA + selector).
// "top 1000 relays" is much more than enough, the limit is mostly to prevent DoS attacks.
const LRU_CACHE_CAPACITY: NonZeroUsize = NonZeroUsize::new(1000).expect("1000 != 0");

/// Normalizes a TXT record RDATA by removing irrelevant characters.
///
/// Some DKIM key records use e.g. LF + WSP line breaks.
/// This is technically not correct, and `viadkim` fails to parse such records,
/// but in practice this is accepted by many implementations.
///
/// Additionally, removes escaped quotes, as such records as:
/// `"...UL9" "\" \"7vGm..."` proved to still be accepted by e.g. dkimpy or OpenDKIM.
fn normalize_rdata(txt_data: &str) -> String {
    txt_data.replace([' ', '\t', '\n', '\r', '"'], "")
}

/// DNS resolver for DKIM TXT records, that caches RDATA in memory.
#[derive(Clone)]
struct CachedResolver {
    dns_resolver: Arc<TokioResolver>,
    // Note: Arc is required despite we are holding the whole handler in an Arc,
    // because viadkim will internally clone the resolver (LookupTxt + Clone + 'static)
    // to parallelize lookups in case of multiple signatures...
    cache: Arc<parking_lot::Mutex<LruCache<Name, Vec<Vec<u8>>>>>,
}

impl CachedResolver {
    /// Creates a new [`CachedResolver`].
    pub fn new(dns_resolver: Arc<TokioResolver>) -> Self {
        let cache = Arc::new(parking_lot::Mutex::new(LruCache::new(LRU_CACHE_CAPACITY)));

        Self {
            dns_resolver,
            cache,
        }
    }

    /// Invalidates the cached RDATA for a given selector and domain.
    ///
    /// Fails silently.
    fn invalidate_cache(&self, selector: &str, domain: &str) {
        let selector_domain_str = format!("{}._domainkey.{}.", selector, domain);
        if let Ok(selector_domain) = Name::from_ascii(&selector_domain_str) {
            let mut cache = self.cache.lock();
            cache.pop(&selector_domain);
            log::debug!("Cache invalidated for {}", selector_domain_str);
        } else {
            log::warn!(
                "Failed to parse selector domain for cache invalidation: {}",
                selector_domain_str
            );
        }
    }
}

impl LookupTxt for CachedResolver {
    type Answer = Box<dyn Iterator<Item = io::Result<Vec<u8>>>>;
    type Query<'a> = Pin<Box<dyn Future<Output = io::Result<Self::Answer>> + Send + 'a>>;

    fn lookup_txt(&self, domain: &str) -> Self::Query<'_> {
        let name = Name::from_ascii(domain);
        Box::pin(async move {
            let name = name.map_err(|_| io::ErrorKind::InvalidInput)?;

            {
                let mut cache = self.cache.lock();
                if let Some(txts) = cache.get(&name) {
                    let txts: Self::Answer = Box::new(txts.clone().into_iter().map(Ok));
                    log::debug!("Using cached TXT records for {}", name);
                    return Ok(txts);
                }
            }

            log::debug!("Trying to resolve TXT records for {}", name);
            let txts: Vec<Vec<u8>> = {
                let lookup = self
                    .dns_resolver
                    .txt_lookup(name.clone())
                    .await
                    .map_err(io::Error::other)?;

                // viadkim would filter out non-DKIM TXT records,
                // but we filter it here anyway so that we know which one should be cached.
                lookup
                    .answers()
                    .iter()
                    .filter(|record| {
                        // Select only TXT records.
                        // When resolving TXT query, CNAMEs are also returned as answers.
                        // We want to filter out CNAMEs first.
                        matches!(record.data, hickory_resolver::proto::rr::RData::TXT(_))
                    })
                    // We don't check all records, as this can be a DoS attack vector.
                    // In theory, selector domains should only have a single TXT record.
                    // In practice, we check at most 3, just in case of weird configuration.
                    .take(3)
                    .map(|txt| {
                        let rdata = txt.data.to_string();
                        log::trace!("TXT (raw rdata): {:?}", rdata);
                        let normalized = normalize_rdata(&rdata);
                        log::trace!("TXT (concatenated and normalized): {:?}", normalized);
                        normalized.into_bytes()
                    })
                    .collect()
            };

            {
                let mut cache = self.cache.lock();
                cache.put(name, txts.clone());
            }

            let txts: Self::Answer = Box::new(txts.into_iter().map(Ok));
            Ok(txts)
        })
    }
}

/// Dummy resolver that always returns the same TXT record, for testing purposes.
#[derive(Clone)]
struct MockResolver(String);

impl LookupTxt for MockResolver {
    type Answer = Box<dyn Iterator<Item = io::Result<Vec<u8>>>>;
    type Query<'a> = Pin<Box<dyn Future<Output = io::Result<Self::Answer>> + Send + 'a>>;

    fn lookup_txt(&self, _domain: &str) -> Self::Query<'_> {
        Box::pin(async move {
            let txts: Self::Answer =
                Box::new(std::iter::once(Ok(normalize_rdata(&self.0).into_bytes())));
            Ok(txts)
        })
    }
}

/// Either a real resolver or a mock.
#[derive(Clone)]
enum Resolver {
    /// A [`CachedResolver`]
    Real(CachedResolver),
    /// A [`MockResolver`]
    Mock(MockResolver),
}

impl LookupTxt for Resolver {
    type Answer = Box<dyn Iterator<Item = io::Result<Vec<u8>>>>;
    type Query<'a> = Pin<Box<dyn Future<Output = io::Result<Self::Answer>> + Send + 'a>>;

    fn lookup_txt(&self, domain: &str) -> Self::Query<'_> {
        match self {
            Resolver::Real(resolver) => resolver.lookup_txt(domain),
            Resolver::Mock(resolver) => resolver.lookup_txt(domain),
        }
    }
}

impl From<CachedResolver> for Resolver {
    fn from(value: CachedResolver) -> Self {
        Resolver::Real(value)
    }
}

impl From<MockResolver> for Resolver {
    fn from(value: MockResolver) -> Self {
        Resolver::Mock(value)
    }
}

/// DKIM verifier using a pre-configured [`viadkim`] verifier, a [`CachedResolver`] for DNS lookups,
/// and strict domain name alignment check.
pub struct DkimVerifier {
    resolver: Resolver,
    config: viadkim::Config,
}

impl DkimVerifier {
    /// Creates a new [`DkimVerifier`] with the provided resolver.
    pub fn new(dns_resolver: Arc<TokioResolver>) -> Self {
        let resolver = CachedResolver::new(dns_resolver).into();
        let config = viadkim::Config {
            lookup_timeout: Duration::from_secs(60),
            ..Default::default()
        };
        Self { resolver, config }
    }

    /// Creates a new [`DkimVerifier`] with a mock resolver that always returns the provided TXT record.
    #[cfg(test)]
    fn mock(txt: String) -> Self {
        let resolver = MockResolver(txt).into();
        let config = viadkim::Config {
            lookup_timeout: Duration::from_secs(60),
            ..Default::default()
        };
        Self { resolver, config }
    }

    /// Verifies the DKIM signature of a raw email message and its alignment with the provided
    /// domain.
    pub async fn verify(&self, raw_mail: &[u8], from_domain: &str) -> Result<(), String> {
        let mail_data = str::from_utf8(raw_mail).or(Err("554 Non-UTF-8 message"))?;
        let (header, body) = mail_data
            .split_once("\r\n\r\n")
            .ok_or("554 Malformed data")?;

        let header = header.parse().map_err(|_| "554 Malformed header")?;

        let Some(mut verifier) =
            viadkim::Verifier::verify_header(&self.resolver, &header, &self.config).await
        else {
            return Err("554 5.7.1 No DKIM signature found".to_string());
        };

        'hasher: for chunk in body.as_bytes().chunks(8192) {
            if verifier.process_body_chunk(chunk) == BodyHasherStance::Done {
                break 'hasher;
            }
        }

        for res in verifier.finish() {
            log::debug!("Signature {}: {:?}", res.index, res.status);

            let Some(signature) = &res.signature else {
                log::debug!("Signature {}: No signature found, skipping", res.index);
                continue;
            };

            if matches!(res.status, VerificationStatus::Failure(_)) {
                log::debug!("Signature {}: Verification failed, skipping", res.index);
                // We only invalidate cache on actual validation error, and not alignment error.
                // TODO: ideally we should retry without cache and swap cached value only on success.
                if let Resolver::Real(resolver) = &self.resolver {
                    resolver
                        .invalidate_cache(signature.selector.as_ref(), signature.domain.as_ref());
                }
                continue;
            }

            if !signature
                .domain
                .to_string()
                .eq_ignore_ascii_case(from_domain)
            {
                log::debug!(
                    "Signature {}: Domain different than in From header, skipping",
                    res.index
                );
                continue;
            }

            return Ok(());
        }

        Err("554 5.7.1 No valid DKIM signature found".to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rstest::rstest;

    #[rstest]
    #[case::simple_simple_canonicalization(
        r#"v=DKIM1;k=rsa;p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA5krC4Xi5Wkr6eMlla38LCFmV645E3FLAgsRl2YJ0SrZ4N2Vw1/yH0mefvtk7HYE7ytV7RQl/er2CkSsaHLJSYLmPCBw5CO6PSsBSXuh6DBqdylh/1t9vVQ9p38fTwn9gU1QvplcpRQL9eepRra1k24VMIaVy2ZZcu3LI9zkPsR7o7TyNaeMhsL8ouWInWc1NSid+p0SgliQuwHIejZhlTPE60JLbJE0OR9I4wmq3377H6z/QrO8XeabCgtmTuzE/hTRyIyNS40jql/99pjlhIcjM2U+P2B0FjwYt7BwLHsgANr74ctlnKY+SdH25rNwVpPmkotaULG5SJCByKBkfCwIDAQAB;s=email;t=s"#,
        include_bytes!("../test_data/dkim-abjadiyah.eml"),
        "abjadiyah.xyz"
    )]
    #[case::txt_escaped_quotes(
        r#"v=DKIM1;k=rsa;p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAu1giTh8KDkEchWhrAB6hGnb+V87kTezkt5I3SP7BGNg8wpv0yAuj/SUmnsttYmcEU+zmNAPqxePmCNvmjLYi/c3YyWEBwHcLyZE9OlS9W4enPdsoCuEN3DayzN4JCV3MsXMedCORvLFXmIARDXDLJUSJeqCeQoudXa9GmF1CrCmx70YyTtV0xOIxEzo7z0DkUL9" "7vGmNJCv6EMpi9wccMKKu8NSmOv+DBw1MLIJqChSZMCs8CYZ5i0KT/+Lijtn6B7wyOcAuQsVL+zr7DWYrFdrePe0wGuivfJ3SvUEfUo1SIykl0nvm0iLGhjNmNa1e/tUw4ULXhQ12Qw685+sq7wIDAQAB;s=email;t=s"#,
        include_bytes!("../test_data/dkim-privitty.eml"),
        "chat.privittytech.com"
    )]
    #[tokio::test]
    async fn test_dkim_verifier(#[case] txt: &str, #[case] message: &[u8], #[case] domain: &str) {
        let verifier = DkimVerifier::mock(txt.to_string());
        verifier.verify(message, domain).await.unwrap();
    }

    #[rstest]
    #[case::escaped_quotes(
        r#"v=DKIM1;k=rsa;p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAu1giTh8KDkEchWhrAB6hGnb+V87kTezkt5I3SP7BGNg8wpv0yAuj/SUmnsttYmcEU+zmNAPqxePmCNvmjLYi/c3YyWEBwHcLyZE9OlS9W4enPdsoCuEN3DayzN4JCV3MsXMedCORvLFXmIARDXDLJUSJeqCeQoudXa9GmF1CrCmx70YyTtV0xOIxEzo7z0DkUL9" "7vGmNJCv6EMpi9wccMKKu8NSmOv+DBw1MLIJqChSZMCs8CYZ5i0KT/+Lijtn6B7wyOcAuQsVL+zr7DWYrFdrePe0wGuivfJ3SvUEfUo1SIykl0nvm0iLGhjNmNa1e/tUw4ULXhQ12Qw685+sq7wIDAQAB;s=email;t=s"#,
        r#"v=DKIM1;k=rsa;p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAu1giTh8KDkEchWhrAB6hGnb+V87kTezkt5I3SP7BGNg8wpv0yAuj/SUmnsttYmcEU+zmNAPqxePmCNvmjLYi/c3YyWEBwHcLyZE9OlS9W4enPdsoCuEN3DayzN4JCV3MsXMedCORvLFXmIARDXDLJUSJeqCeQoudXa9GmF1CrCmx70YyTtV0xOIxEzo7z0DkUL97vGmNJCv6EMpi9wccMKKu8NSmOv+DBw1MLIJqChSZMCs8CYZ5i0KT/+Lijtn6B7wyOcAuQsVL+zr7DWYrFdrePe0wGuivfJ3SvUEfUo1SIykl0nvm0iLGhjNmNa1e/tUw4ULXhQ12Qw685+sq7wIDAQAB;s=email;t=s"#
    )]
    fn test_normalize_rdata(#[case] input: &str, #[case] expected: &str) {
        assert_eq!(normalize_rdata(input), expected);
    }
}
