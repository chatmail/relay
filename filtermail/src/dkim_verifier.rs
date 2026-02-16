use hickory_resolver::name_server::TokioConnectionProvider;
use hickory_resolver::{Name, TokioResolver};
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

/// DNS resolver for DKIM TXT records, that caches RDATA in memory.
#[derive(Clone)]
struct CachedResolver {
    dns_resolver: TokioResolver,
    // Note: Arc is required despite we are holding the whole handler in an Arc,
    // because viadkim will internally clone the resolver (LookupTxt + Clone + 'static)
    // to parallelize lookups in case of multiple signatures...
    cache: Arc<parking_lot::Mutex<LruCache<Name, Vec<u8>>>>,
}

impl CachedResolver {
    /// Creates a new [`CachedResolver`].
    pub fn new() -> Result<Self, crate::error::Error> {
        // Use resolv.conf
        let dns_resolver = TokioResolver::builder(TokioConnectionProvider::default())?.build();

        let cache = Arc::new(parking_lot::Mutex::new(LruCache::new(LRU_CACHE_CAPACITY)));

        Ok(Self {
            dns_resolver,
            cache,
        })
    }

    /// Normalizes a TXT record RDATA by removing whitespace characters.
    ///
    /// Some DKIM key records use e.g. LF + WSP line breaks.
    /// This is technically not correct, and `viadkim` fails to parse such records,
    /// but in practice this is accepted by many implementations.
    fn normalize_rdata(txt_data: &str) -> String {
        txt_data.replace([' ', '\t', '\n', '\r'], "")
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
                if let Some(rdata) = cache.get(&name) {
                    let txts: Self::Answer = Box::new(std::iter::once(Ok(rdata.clone())));
                    log::debug!("Using cached RDATA for {}", name);
                    return Ok(txts);
                }
            }

            log::debug!("Trying to resolve TXT for {}", name);
            let txt = {
                let lookup = self.dns_resolver.txt_lookup(name.clone()).await?;

                // viadkim would filter out non-DKIM TXT records,
                // but we filter it here anyway so that we know which one should be cached.
                lookup
                    .into_iter()
                    .find_map(|txt| {
                        let rdata_raw = txt.txt_data().concat();
                        let rdata = String::from_utf8_lossy(&rdata_raw);
                        // naive check, but this can't be an attack vector,
                        // and selector domain should only have a single TXT record anyway.
                        if rdata.contains("DKIM") {
                            Some(Self::normalize_rdata(&rdata).into_bytes())
                        } else {
                            None
                        }
                    })
                    .ok_or(io::ErrorKind::NotFound)?
            };

            {
                let mut cache = self.cache.lock();
                cache.put(name, txt.clone());
            }

            let txts: Self::Answer = Box::new(std::iter::once(Ok(txt)));
            Ok(txts)
        })
    }
}

/// DKIM verifier using a pre-configured [`viadkim`] verifier, a [`CachedResolver`] for DNS lookups,
/// and strict domain name alignment check.
pub struct DkimVerifier {
    resolver: CachedResolver,
    config: viadkim::Config,
}

impl DkimVerifier {
    /// Creates a new [`DkimVerifier`] with the provided resolver.
    pub fn new() -> Result<Self, crate::error::Error> {
        let resolver = CachedResolver::new()?;
        let config = viadkim::Config {
            lookup_timeout: Duration::from_secs(60),
            ..Default::default()
        };
        Ok(Self { resolver, config })
    }

    /// Verifies the DKIM signature of a raw email message and its alignment with the provided
    /// domain.
    pub async fn verify(&self, raw_mail: &[u8], from_domain: &str) -> Result<(), String> {
        let (headers, body_start) = {
            use viadkim::{FieldBody, FieldName, HeaderField};

            let Ok((headers, body_start)) = mailparse::parse_headers(raw_mail) else {
                return Err("500 Failed to parse message headers".to_string());
            };

            let mut viadkim_headers: Vec<HeaderField> = Vec::new();
            for header in headers {
                match (
                    FieldName::new(header.get_key()),
                    FieldBody::new(header.get_value_raw()),
                ) {
                    (Ok(name), Ok(body)) => viadkim_headers.push((name, body)),
                    (Err(e), _) | (_, Err(e)) => {
                        log::debug!("Failed to parse header {header:?}, skipping: {e}");
                    }
                }
            }

            let viadkim_headers = viadkim::HeaderFields::new(viadkim_headers).map_err(|e| {
                log::error!("Failed to parse headers for DKIM verification: {e}");
                "500 Failed to parse message headers".to_string()
            })?;

            (viadkim_headers, body_start)
        };

        let Some(mut verifier) =
            viadkim::Verifier::verify_header(&self.resolver, &headers, &self.config).await
        else {
            return Err("554 5.7.1 No DKIM signature found".to_string());
        };

        'hasher: for chunk in raw_mail.get(body_start..).unwrap_or_default().chunks(8192) {
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
                self.resolver
                    .invalidate_cache(signature.selector.as_ref(), signature.domain.as_ref());
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
