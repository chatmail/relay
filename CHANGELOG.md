# Changelog for chatmail deployment 

## 1.9.0 2025-12-18

### Documentation

- Add RELEASE.md and CONTRIBUTING.md
- README update, mention Chatmail Cookbook project

### Bug Fixes

- Expire messages also from IMAP subfolders
- Use absolute path instead of relative path in message expiration script
- Restart Postfix and Dovecot automatically on failure
- acmetool: Use a fixed name and `reconcile` instead of `want`

### Features

- Report DKIM error code in SMTP response
- Remove development notice from the web pages

### Miscellaneous Tasks

- Update the heading in the CHANGELOG.md
- Setup git-cliff
- Run tests against ci-chatmail.testrun.org instead of nine.testrun.org
- Cleanup remaining echobot code, remove echobot user from deployment and passthrough recipients

## 1.8.0 2025-12-12

- Add imap_compress option to chatmail.ini
  ([#760](https://github.com/chatmail/relay/pull/760))

- Remove echobot from relays 
  ([#753](https://github.com/chatmail/relay/pull/753))

- Fix `cmdeploy webdev`
  ([#743](https://github.com/chatmail/relay/pull/743))

- Add robots.txt to exclude all web crawlers
  ([#732](https://github.com/chatmail/relay/pull/732))

- acmetool: accept new Let's Encrypt ToS: https://letsencrypt.org/documents/LE-SA-v1.6-August-18-2025.pdf
  ([#729](https://github.com/chatmail/relay/pull/729))

- Organized cmdeploy into install, configure, and activate stages
  ([#695](https://github.com/chatmail/relay/pull/695))

- docs: move readme.md docs to sphinx documentation rendered at https://chatmail.at/doc/relay 
  ([#711](https://github.com/chatmail/relay/pull/711))

- acmetool: replace cronjob with a systemd timer
  ([#719](https://github.com/chatmail/relay/pull/719))

- remove xstore@testrun.org from default passthrough recipients
  ([#722](https://github.com/chatmail/relay/pull/722))

- don't deploy the website if there are merge conflicts in the www folder
  ([#714](https://github.com/chatmail/relay/pull/714))

- acmetool: use ECDSA keys instead of RSA
  ([#689](https://github.com/chatmail/relay/pull/689))

- Require TLS 1.2 for outgoing SMTP connections
  ([#685](https://github.com/chatmail/relay/pull/685), [#730](https://github.com/chatmail/relay/pull/730))

- require STARTTLS for incoming port 25 connections
  ([#684](https://github.com/chatmail/relay/pull/684), [#730](https://github.com/chatmail/relay/pull/730))

- filtermail: run CPU-intensive handle_DATA in a thread pool executor
  ([#676](https://github.com/chatmail/relay/pull/676))

- don't use the complicated logging module in filtermail to exclude a potential source of errors. 
  ([#674](https://github.com/chatmail/relay/pull/674))

- Specify nginx.conf to only handle `mail_domain`, www, and mta-sts domains
  ([#636](https://github.com/chatmail/relay/pull/636))

- Setup TURN server
  ([#621](https://github.com/chatmail/relay/pull/621))

- cmdeploy: make --ssh-host work with localhost
  ([#659](https://github.com/chatmail/relay/pull/659))

- Update iroh-relay to 0.35.0
  ([#650](https://github.com/chatmail/relay/pull/650))

- filtermail: accept mails from Protonmail
  ([#616](https://github.com/chatmail/relay/pull/616))

- Ignore all RCPT TO: parameters
  ([#651](https://github.com/chatmail/relay/pull/651))

- Increase opendkim DNS Timeout from 5 to 60 seconds
  ([#672](https://github.com/chatmail/relay/pull/672))

- Add config parameter for Let's Encrypt ACME email
  ([#663](https://github.com/chatmail/relay/pull/663))

- Use max username length in newemail.py, not min
  ([#648](https://github.com/chatmail/relay/pull/648))

- Add startup for `fcgiwrap.service` because sometimes it did not start automatically.
  ([#657](https://github.com/chatmail/relay/pull/657))

- Add `cmdeploy init --force` command for recreating chatmail.ini
  ([#656](https://github.com/chatmail/relay/pull/656))

- Increase maxproc for reinjecting ports from 10 to 100
  ([#646](https://github.com/chatmail/relay/pull/646))

- Allow ports 143 and 993 to be used by `dovecot` process
  ([#639](https://github.com/chatmail/relay/pull/639))

- Add `--skip-dns-check` argument to `cmdeploy run` command, which disables DNS record checking before installation.
  ([#661](https://github.com/chatmail/relay/pull/661))

- Rework expiry of message files and mailboxes in Python 
  to only do a single iteration over sometimes millions of messages
  instead of doing "find" commands that iterate 9 times over the messages. 
  Provide an "fsreport" CLI for more fine grained analysis of message files. 
  ([#637](https://github.com/chatmail/relay/pull/637))


## 1.7.0 2025-09-11

- Make www upload path configurable
  ([#618](https://github.com/chatmail/relay/pull/618))

- Check whether GCC is installed in initenv.sh
  ([#608](https://github.com/chatmail/relay/pull/608))

- Expire push notification tokens after 90 days
  ([#583](https://github.com/chatmail/relay/pull/583))

- Use official `mtail` binary instead of `mtail` package
  ([#581](https://github.com/chatmail/relay/pull/581))

- dovecot: install from download.delta.chat instead of openSUSE Build Service
  ([#590](https://github.com/chatmail/relay/pull/590))

- Reconfigure Dovecot imap-login service to high-performance mode
  ([#578](https://github.com/chatmail/relay/pull/578))

- Set timezone to improve dovecot performance
  ([#584](https://github.com/chatmail/relay/pull/584))

- Increase nginx connection limits
  ([#576](https://github.com/chatmail/relay/pull/576))

- If `dns-utils` needs to be installed before cmdeploy run, apt update to make sure it works
  ([#560](https://github.com/chatmail/relay/pull/560))

- filtermail: respect config message size limit
  ([#572](https://github.com/chatmail/relay/pull/572))

- Don't deploy if one of the ports used for chatmail relay services is occupied by an unexpected process
  ([#568](https://github.com/chatmail/relay/pull/568))

- Add config value after how many days large files are deleted
  ([#555](https://github.com/chatmail/relay/pull/555))

- cmdeploy: push relay version to /etc/chatmail-version
  ([#573](https://github.com/chatmail/relay/pull/573))

- filtermail: allow partial body length in OpenPGP payloads
  ([#570](https://github.com/chatmail/relay/pull/570))

- chatmaild: allow echobot to receive unencrypted messages by default
  ([#556](https://github.com/chatmail/relay/pull/556))


## 1.6.0 2025-04-11

- Handle Port-25 connect errors more gracefully (common with VPNs)
  ([#552](https://github.com/chatmail/relay/pull/552))

- Avoid "acmetool not found" during initial run
  ([#550](https://github.com/chatmail/relay/pull/550))

- Fix timezone handling such that client/servers do not need to use
  same timezone. 
  ([#553](https://github.com/chatmail/relay/pull/553))

- Enforce end-to-end encryption for incoming messages. 
  New user address mailboxes now get a `enforceE2EEincoming` file 
  which prohibits incoming cleartext messages from other domains. 
  An outside MTA trying to submit a cleartext message will 
  get a "523 Encryption Needed" response, see RFC5248. 
  If the file does not exist (as it the case for all existing accounts) 
  incoming cleartext messages are accepted. 
  ([#538](https://github.com/chatmail/server/pull/538))

- Enforce end-to-end encryption between local addresses 
  ([#535](https://github.com/chatmail/server/pull/535))

- unbound: check that port 53 is not occupied by a different process
  ([#537](https://github.com/chatmail/server/pull/537))

- unbound: before unbound is there, use 9.9.9.9 for resolving
  ([#518](https://github.com/chatmail/relay/pull/518))

- Limit the bind for the HTTPS server on 8443 to 127.0.0.1 
  ([#522](https://github.com/chatmail/server/pull/522))
  ([#532](https://github.com/chatmail/server/pull/532))

- Send SNI when connecting to outside servers
  ([#524](https://github.com/chatmail/server/pull/524))

- postfix master.cf: use 127.0.0.1 for consistency
  ([#544](https://github.com/chatmail/relay/pull/544))

- Pass through `original_content` instead of `content` in filtermail
  ([#509](https://github.com/chatmail/server/pull/509))

- Document TLS requirements in the readme
  ([#514](https://github.com/chatmail/server/pull/514))

- Remove cleanup service from submission ports
  ([#512](https://github.com/chatmail/server/pull/512))

- cmdeploy dovecot: delete big messages after 7 days
  ([#504](https://github.com/chatmail/server/pull/504))

- mtail: fix getting logs from STDIN
  ([#502](https://github.com/chatmail/server/pull/502))

- filtermail: don't require exactly 2 lines after openPGP payload
  ([#497](https://github.com/chatmail/server/pull/497))

- cmdeploy dns: offer alternative DKIM record format for some web interfaces
  ([#470](https://github.com/chatmail/server/pull/470))

- journald: remove old logs from disk
  ([#490](https://github.com/chatmail/server/pull/490))

- opendkim: restart once every day to mend RAM leaks
  ([#498](https://github.com/chatmail/server/pull/498)

- migration guide: let opendkim own the DKIM keys directory
  ([#468](https://github.com/chatmail/server/pull/468))

- improve secure-join message detection
  ([#473](https://github.com/chatmail/server/pull/473))

- use old crypt lib in python < 3.11
  ([#483](https://github.com/chatmail/server/pull/483))

- chatmaild: set umask to 0700 for doveauth + metadata
  ([#490](https://github.com/chatmail/server/pull/492))

- remove MTA-STS daemon
  ([#488](https://github.com/chatmail/server/pull/488))

- replace `Subject` with `[...]` for all outgoing mails.
  ([#481](https://github.com/chatmail/server/pull/481))

- opendkim: use su instead of sudo
  ([#491](https://github.com/chatmail/server/pull/491))

## 1.5.0 2024-12-20

- cmdeploy dns: always show recommended DNS records
  ([#463](https://github.com/chatmail/server/pull/463))

- add `--all` to `cmdeploy dns`
  ([#462](https://github.com/chatmail/server/pull/462))

- fix `_mta-sts` TXT DNS record
  ([#461](https://github.com/chatmail/server/pull/461)

- deploy `iroh-relay` and also update "realtime relay services" in privacy policy. 
  ([#434](https://github.com/chatmail/server/pull/434))
  ([#451](https://github.com/chatmail/server/pull/451))

- add guide to migrate chatmail to a new server
  ([#429](https://github.com/chatmail/server/pull/429))

- disable anvil authentication penalty
  ([#414](https://github.com/chatmail/server/pull/444)

- increase `request_queue_size` for UNIX sockets to 1000.
  ([#437](https://github.com/chatmail/server/pull/437))

- add argument to `cmdeploy run` for specifying
  a different SSH host than `mail_domain`
  ([#439](https://github.com/chatmail/server/pull/439))

- query autoritative nameserver to bypass DNS cache
  ([#424](https://github.com/chatmail/server/pull/424))

- add mtail support (new optional `mtail_address` ini value)
  This defines the address on which [`mtail`](https://google.github.io/mtail/)
  exposes its metrics collected from the logs.
  If you want to collect the metrics with Prometheus,
  setup a private network (e.g. WireGuard interface)
  and assign an IP address from this network to the host.
  If you do not plan to collect metrics,
  keep this setting unset.
  ([#388](https://github.com/chatmail/server/pull/388))

- fix checking for required DNS records
  ([#412](https://github.com/chatmail/server/pull/412))

- add support for specifying whole domains for recipient passthrough list
  ([#408](https://github.com/chatmail/server/pull/408))

- add a paragraph about "account deletion" to info page 
  ([#405](https://github.com/chatmail/server/pull/405))

- avoid nginx listening on ipv6 if v6 is dsiabled 
  ([#402](https://github.com/chatmail/server/pull/402))

- refactor ssh-based execution to allow organizing remote functions in
  modules. 
  ([#396](https://github.com/chatmail/server/pull/396))

- trigger "apt upgrade" during "cmdeploy run" 
  ([#398](https://github.com/chatmail/server/pull/398))

- drop hispanilandia passthrough address
  ([#401](https://github.com/chatmail/server/pull/401))

- set CAA record flags to 0

- add IMAP capabilities instead of overwriting them
  ([#413](https://github.com/chatmail/server/pull/413))

- fix OpenPGP payload check
  ([#435](https://github.com/chatmail/server/pull/435))

- fix Dovecot quota_max_mail_size to use max_message_size config value
  ([#438](https://github.com/chatmail/server/pull/438))


## 1.4.1 2024-07-31

- fix metadata dictproxy which would confuse transactions
  resulting in missed notifications and other issues. 
  ([#393](https://github.com/chatmail/server/pull/393))
  ([#394](https://github.com/chatmail/server/pull/394))

- add optional "imap_rawlog" config option. If true, 
  .in/.out files are created in user home dirs 
  containing the imap protocol messages. 
  ([#389](https://github.com/chatmail/server/pull/389))

## 1.4.0 2024-07-28

- Add `disable_ipv6` config option to chatmail.ini.
  Required if the server doesn't have IPv6 connectivity.
  ([#312](https://github.com/chatmail/server/pull/312))

- allow current K9/Thunderbird-mail releases to send encrypted messages
  outside by accepting their localized "encrypted subject" strings. 
  ([#370](https://github.com/chatmail/server/pull/370))

- Migrate and remove sqlite database in favor of password/lastlogin tracking 
  in a user's maildir.  
  ([#379](https://github.com/chatmail/server/pull/379))

- Require pyinfra V3 installed on the client side,
  run `./scripts/initenv.sh` to upgrade locally.
  ([#378](https://github.com/chatmail/server/pull/378))

- don't hardcode "/home/vmail" paths but rather set them 
  once in the config object and use it everywhere else, 
  thereby also improving testability.  
  ([#351](https://github.com/chatmail/server/pull/351))
  temporarily introduced obligatory "passdb_path" and "mailboxes_dir" 
  settings but they were removed/obsoleted in 
  ([#380](https://github.com/chatmail/server/pull/380))

- BREAKING: new required chatmail.ini value 'delete_inactive_users_after = 100'
  which removes users from database and mails after 100 days without any login. 
  ([#350](https://github.com/chatmail/server/pull/350))

- Refine DNS checking to distinguish between "required" and "recommended" settings 
  ([#372](https://github.com/chatmail/server/pull/372))

- reload nginx in the acmetool cronjob
  ([#360](https://github.com/chatmail/server/pull/360))

- remove checking of reverse-DNS PTR records.  Chatmail-servers don't
  depend on it and even in the wider e-mail system it's not common anymore. 
  If it's an issue, a chatmail operator can still care to properly set reverse DNS. 
  ([#348](https://github.com/chatmail/server/pull/348))

- Make DNS-checking faster and more interactive, run it fully during "cmdeploy run",
  also introducing a generic mechanism for rapid remote ssh-based python function execution. 
  ([#346](https://github.com/chatmail/server/pull/346))

- Don't fix file owner ship of /home/vmail 
  ([#345](https://github.com/chatmail/server/pull/345))

- Support iterating over all users with doveadm commands 
  ([#344](https://github.com/chatmail/server/pull/344))

- Test and fix for attempts to create inadmissible accounts 
  ([#333](https://github.com/chatmail/server/pull/321))

- check that OpenPGP has only PKESK, SKESK and SEIPD packets
  ([#323](https://github.com/chatmail/server/pull/323),
   [#324](https://github.com/chatmail/server/pull/324))

- improve filtermail checks for encrypted messages and drop support for unencrypted MDNs
  ([#320](https://github.com/chatmail/server/pull/320))

- replace `bash` with `/bin/sh`
  ([#334](https://github.com/chatmail/server/pull/334))

- Increase number of logged in IMAP sessions to 50000
  ([#335](https://github.com/chatmail/server/pull/335))

- filtermail: do not allow ASCII armor without actual payload
  ([#325](https://github.com/chatmail/server/pull/325))

- Remove sieve to enable hardlink deduplication in LMTP
  ([#343](https://github.com/chatmail/server/pull/343))

- dovecot: enable gzip compression on disk
  ([#341](https://github.com/chatmail/server/pull/341))

- DKIM-sign Content-Type and oversign all signed headers
  ([#296](https://github.com/chatmail/server/pull/296))

- Add nonci_accounts metric
  ([#347](https://github.com/chatmail/server/pull/347))

- doveauth: log when a new account is created
  ([#349](https://github.com/chatmail/server/pull/349))

- Multiplex HTTPS, IMAP and SMTP on port 443
  ([#357](https://github.com/chatmail/server/pull/357))

## 1.3.0 - 2024-06-06

- don't check necessary DNS records on cmdeploy init anymore
  ([#316](https://github.com/chatmail/server/pull/316))

- ensure cron and acl are installed
  ([#293](https://github.com/chatmail/server/pull/293),
  [#310](https://github.com/chatmail/server/pull/310))

- change default for delete_mails_after from 40 to 20 days
  ([#300](https://github.com/chatmail/server/pull/300))

- save journald logs only to memory and save nginx logs to journald instead of file
  ([#299](https://github.com/chatmail/server/pull/299))

- fix writing of multiple obs repositories in `/etc/apt/sources.list`
  ([#290](https://github.com/chatmail/server/pull/290))

- metadata: add support for `/shared/vendor/deltachat/irohrelay`
  ([#284](https://github.com/chatmail/server/pull/284))

- Emit "XCHATMAIL" capability from IMAP server 
  ([#278](https://github.com/chatmail/server/pull/278))

- Move echobot `into /var/lib/echobot`
  ([#281](https://github.com/chatmail/server/pull/281))

- Accept Let's Encrypt's new Terms of Services
  ([#275](https://github.com/chatmail/server/pull/276))

- Reload Dovecot and Postfix when TLS certificate updates
  ([#271](https://github.com/chatmail/server/pull/271))

- Use forked version of dovecot without hardcoded delays
  ([#270](https://github.com/chatmail/server/pull/270))

## 1.2.0 - 2024-04-04

- Install dig on the server to resolve DNS records
  ([#267](https://github.com/chatmail/server/pull/267))

- preserve notification order and exponentially backoff with 
  retries for tokens where we didn't get a successful return
  ([#265](https://github.com/chatmail/server/pull/263))

- Run chatmail-metadata and doveauth as vmail
  ([#261](https://github.com/chatmail/server/pull/261))

- Apply systemd restrictions to echobot
  ([#259](https://github.com/chatmail/server/pull/259))

- re-enable running the CI in pull requests, but not concurrently 
  ([#258](https://github.com/chatmail/server/pull/258))


## 1.1.0 - 2024-03-28

### The changelog starts to record changes from March 15th, 2024 

- Move systemd unit templates to cmdeploy package 
  ([#255](https://github.com/chatmail/server/pull/255))

- Persist push tokens and support multiple device per address 
  ([#254](https://github.com/chatmail/server/pull/254))

- Avoid warning for regular doveauth protocol's hello message. 
  ([#250](https://github.com/chatmail/server/pull/250))

- Fix various tests to pass again with "cmdeploy test". 
  ([#245](https://github.com/chatmail/server/pull/245),
  [#242](https://github.com/chatmail/server/pull/242)

- Ensure lets-encrypt certificates are reloaded after renewal 
  ([#244]) https://github.com/chatmail/server/pull/244

- Persist tokens to avoid iOS users loosing push-notifications when the
  chatmail metadata service is restarted (happens regularly during deploys)
  ([#238](https://github.com/chatmail/server/pull/239)

- Fix failing sieve-script compile errors on incoming messages
  ([#237](https://github.com/chatmail/server/pull/239)

- Fix quota reporting after expunging of old mails
  ([#233](https://github.com/chatmail/server/pull/239)
