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
