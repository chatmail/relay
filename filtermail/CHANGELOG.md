## 0.7.2 - 2026-06-26

### Documentation

- *(readme)* Disable colors in mermaid diagrams (#180)
- *(readme)* Update Transport mode doc

### Features

- *(transport)* Destination worker pool

### Refactor

- Implement Display for AddressDomain

### Testing

- Test filtermail-transport
## 0.7.1 - 2026-06-09

### Bug Fixes

- Switch ratelimiter to MonotonicClock (#167)
- *(smtp-server)* Correct error when EOF while reading DATA (#168)
- *(resolver)* Disable negative caching (#170)
- Ignore CNAME records when resolving TXT records (#177)

### Features

- Switch to aws-lc-rs cryptography provider (#178)

### Miscellaneous Tasks

- Add filtermail.mtail so filtermail failures can be monitored (#169)
## 0.7.0 - 2026-05-26

### Bug Fixes

- Do not crash if accepting new connection fails

### Documentation

- *(readme)* Remove docs for options removed in da9a116 (#162)

### Features

- [**breaking**] Remove passthrough options that allowed unencrypted mail to pass
## 0.6.6 - 2026-05-12

### Bug Fixes

- Return HTTP 200 because madmail expects it, and make sure https is immediately retried when SMTP fails (#153)

### Features

- Improved SMTP error responses (#147)

### Miscellaneous Tasks

- Remove mac and windows from matrix tests (#154)
- Run cmlxc tests in all classic/classic-ipv4/madmail combinations
## 0.6.5 - 2026-05-12

### Bug Fixes

- *(smtp-client)* Handle 421 on reused connection (#145)
- Advertise 8BITMIME to prevent conversion after DKIM signing (#149)
- Validate mail data (#150)

### Miscellaneous Tasks

- Build and deploy relays with filtermail binary and run interop tests against madmail  (#131)

### Performance

- *(smtp-client)* Use pipelining if server advertises support (#146)
## 0.6.4 - 2026-05-01

### Bug Fixes

- Implement missing "implicit MX" rule

### Features

- Https transport channel (#122)

### Refactor

- *(transport)* Explicitly handle RFC7505 null MX
## 0.6.3 - 2026-04-20

### Features

- *(smtp-server)* Log malformed SMTP commands (#118)

### Performance

- *(smtp-client)* Cache connections (#117)
## 0.6.2 - 2026-04-16

### Documentation

- *(readme)* Reformat README.md (#115)

### Features

- Log disabled recipients (#113)
- *(transport)* Remote delivery over SMTP (#104)

### Miscellaneous Tasks

- *(dependabot)* Update configuration (#114)
## 0.6.1 - 2026-04-01

### Documentation

- *(readme)* Fix typo (#99)

### Features

- Configurable hosts for listen and reinject (#84)
- *(resolver)* Enable DNSSEC (#94)
- Add experimental option to disable mailboxes (#108)

### Refactor

- Derive Default for Envelope (#100)
## 0.6.0 - 2026-03-13

### Documentation

- *(readme)* Fix license link
- *(readme)* Clarify licensing of the binaries
- *(readme)* Improve README.md (#88)

### Features

- [**breaking**] Remove IP verification for domain-literals (#90)

### Miscellaneous Tasks

- *(ci)* Fix binary publish job (#79)

### Refactor

- Use enum for mode cli arg (#83)
## 0.5.2 - 2026-02-27

### Bug Fixes

- *(logs)* Log correct address for outbound messages (#70)

### Features

- Check incoming email return address (#72)

### Miscellaneous Tasks

- Bump cargo-dist (#73)
- *(ci)* Build and upload binaries in CI (#76)
- *(ci)* Add missing Zig dependency (#77)

### Refactor

- Check if email is encrypted before verifying DKIM (#71)
## 0.5.1 - 2026-02-24

### Bug Fixes

- *(dkim)* Accept TXT records with no `v=` tag (#62)
- *(smtp)* Properly handle bounce messages (#63)
- *(dkim)* Accept TXT records with escaped quotes (#61)
- *(logs)* Log `From` address instead of envelope `MAIL FROM`. (#66)
## 0.5.0 - 2026-02-20

### Bug Fixes

- *(dkim)* Make simple header canonicalization work properly (#53)

### Features

- Save rejected messages to `/tmp` (#55)

### Refactor

- Do not copy the mail in memory for DKIM verification (#54)
## 0.4.1 - 2026-02-17

### Miscellaneous Tasks

- *(tests)* Add a way to disable DKIM for tests (#50)
## 0.4.0 - 2026-02-17

### Features

- [**breaking**] DKIM verifier (#35)
- Support addresses using domain literals (#42)
## 0.3.0 - 2026-02-14

### Features

- Support legacy, pre-OpenPGP packet format (#44)

### Miscellaneous Tasks

- *(dist)* Switch to musl targets (#31)

### Refactor

- Remove unnecessary Arc (#36)
- Use a custom, minimal SMTP client instead of lettre (#33)
## 0.2.0 - 2026-01-28

### Features

- Configurable rate limiter max burst size (#28)

### Performance

- Disable Nagle's algorithm and do own buffering on server connections

### Refactor

- Remove Mutex around rate limiter
## 0.1.2 - 2026-01-22

### Bug Fixes

- Set logs required by grafana to INFO (#21)
- Make inbound/outbound log messages consistent (#23)

### Performance

- Use governor for rate limiting (#20)
## 0.1.1 - 2026-01-21

### Bug Fixes

- Improve address extraction from SMTP commands (#14)
- Correct a typo in SMTP answer (#11)
- *(config)* Set default values for internal SMTP ports and max message size (#12)

### Features

- Improve logging (#13)

### Miscellaneous Tasks

- *(dist)* Configure cargo-dist (#10)
- Configure git-cliff

### Refactor

- Get rid of indexing and slicing in check_armored_payload() (#15)
- Apply more lints (#17)
## 0.1.0 - 2026-01-19

### Documentation

- *(readme)* Add README.md
- *(license)* Add LICENSE

### Features

- Initial implementation

### Miscellaneous Tasks

- Init repository
- *(dependabot)* Setup dependabot
- *(ci)* Setup CI
- *(dependabot)* Add github-actions to dependabot
- *(cargo)* Add metadata
