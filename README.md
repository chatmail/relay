
<img width="800px" src="www/src/collage-top.png"/>

# Chatmail relays for end-to-end encrypted e-mail

Chatmail relay servers are interoperable Mail Transport Agents (MTAs) designed for: 

- **Convenience:** Low friction instant onboarding

- **Privacy:** No name, phone numbers, email required or collected 

- **End-to-End Encryption enforced**: only OpenPGP messages with metadata minimization allowed 

- **Instant:** Privacy-preserving Push Notifications for Apple, Google, and Huawei

- **Speed:** Message delivery in half a second, with optional P2P realtime connections 

- **Transport Security:** Strict TLS and DKIM enforced 

- **Reliability:** No spam or IP reputation checks; rate-limits are suitable for realtime chats

- **Efficiency:** Messages are only stored for transit and removed automatically

This repository contains everything needed to setup a ready-to-use chatmail relay
comprised of a minimal setup of the battle-tested 
[Postfix SMTP](https://www.postfix.org) and [Dovecot IMAP](https://www.dovecot.org) MTAs/MDAs.

The automated setup is designed and optimized for providing chatmail addresses
for immediate permission-free onboarding through chat apps and bots.
Chatmail addresses are automatically created at first login,
after which the initially specified password is required
for sending and receiving messages through them.

Please see [this list of known apps and client projects](https://chatmail.at/clients.html) 
and [this list of known public 3rd party chatmail relay servers](https://chatmail.at/relays).


## Minimal requirements, Prerequisites 

You will need the following: 

- Control over a domain through a DNS provider of your choice.

- A Debian 12 server with reachable SMTP/SUBMISSIONS/IMAPS/HTTPS ports.
  IPv6 is encouraged if available.
  Chatmail relay servers only require 1GB RAM, one CPU, and perhaps 10GB storage for a
  few thousand active chatmail addresses.

- Key-based SSH authentication to the root user.
  You must add a passphrase-protected private key to your local ssh-agent
  because you can't type in your passphrase during deployment.
  (An ed25519 private key is required due to an [upstream bug in paramiko](https://github.com/paramiko/paramiko/issues/2191))


## Getting started 

We use `chat.example.org` as the chatmail domain in the following steps.
Please substitute it with your own domain. 

1. Setup the initial DNS records.
   The following is an example in the familiar BIND zone file format with
   a TTL of 1 hour (3600 seconds).
   Please substitute your domain and IP addresses.

   ```
    chat.example.com. 3600 IN A 198.51.100.5
    chat.example.com. 3600 IN AAAA 2001:db8::5
    www.chat.example.com. 3600 IN CNAME chat.example.com.
    mta-sts.chat.example.com. 3600 IN CNAME chat.example.com.
   ```

2. Clone the repository and bootstrap the Python virtualenv.

   ```
    git clone https://github.com/chatmail/relay
    cd relay
    scripts/initenv.sh
   ```

3. Create chatmail configuration file `chatmail.ini`:

   ```
    scripts/cmdeploy init chat.example.org  # <-- use your domain 
   ```

4. Verify that SSH root login works:

   ```
    ssh root@chat.example.org   # <-- use your domain 
   ```


5. Deploy the remote chatmail relay server:

   ```
    scripts/cmdeploy run
   ```
   This script will check that you have all necessary DNS records.
   If DNS records are missing, it will recommend
   which you should configure at your DNS provider
   (it can take some time until they are public).

### Other helpful commands:

To check the status of your remotely running chatmail service:

```
scripts/cmdeploy status
```

To display and check all recommended DNS records:

```
scripts/cmdeploy dns
```

To test whether your chatmail service is working correctly:

```
scripts/cmdeploy test
```

To measure the performance of your chatmail service:

```
scripts/cmdeploy bench
```

## Overview of this repository

This repository has four directories:

- [cmdeploy](https://github.com/chatmail/relay/tree/main/cmdeploy)
  is a collection of configuration files
  and a [pyinfra](https://pyinfra.com)-based deployment script.

- [chatmaild](https://github.com/chatmail/relay/tree/main/chatmaild)
  is a Python package containing several small services
  which handle authentication,
  trigger push notifications on new messages,
  ensure that outbound mails are encrypted,
  delete inactive users,
  and some other minor things.
  chatmaild can also be installed as a stand-alone Python package.

- [www](https://github.com/chatmail/relay/tree/main/www)
  contains the html, css, and markdown files
  which make up a chatmail relay's web page.
  Edit them before deploying to make your chatmail relay stand out.

- [scripts](https://github.com/chatmail/relay/tree/main/scripts)
  offers two convenience tools for beginners;
  `initenv.sh` installs the necessary dependencies to a local virtual environment,
  and the `scripts/cmdeploy` script enables you
  to run the `cmdeploy` command line tool in the local virtual environment.

### cmdeploy

The `cmdeploy/src/cmdeploy/cmdeploy.py` command line tool
helps with setting up and managing the chatmail service.
`cmdeploy init` creates the `chatmail.ini` config file.
`cmdeploy run` uses a [pyinfra](https://pyinfra.com/)-based [`script`](cmdeploy/src/cmdeploy/__init__.py)
to automatically install or upgrade all chatmail components on a relay,
according to the `chatmail.ini` config.

The components of chatmail are:

- [Postfix SMTP MTA](https://www.postfix.org) accepts and relays messages
  (both from your users and from the wider e-mail MTA network)

- [Dovecot IMAP MDA](https://www.dovecot.org) stores messages for your users until they download them

- [Nginx](https://nginx.org/) shows the web page with your privacy policy and additional information

- [acmetool](https://hlandau.github.io/acmetool/) manages TLS certificates for Dovecot, Postfix, and Nginx

- [OpenDKIM](http://www.opendkim.org/) for signing messages with DKIM and rejecting inbound messages without DKIM

- [mtail](https://google.github.io/mtail/) for collecting anonymized metrics in case you have monitoring

- [Iroh relay](https://www.iroh.computer/docs/concepts/relay) 
  which helps client devices to establish Peer-to-Peer connections 

- and the chatmaild services, explained in the next section:

### chatmaild

`chatmaild` implements various systemd-controlled services  
that integrate with Dovecot and Postfix to achieve instant-onboarding and 
only relaying OpenPGP end-to-end messages encrypted messages. 
A short overview of `chatmaild` services: 

- [`doveauth`](https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/doveauth.py) 
  implements create-on-login address semantics and is used 
  by Dovecot during IMAP login and by Postfix during SMTP/SUBMISSION login
  which in turn uses [Dovecot SASL](https://doc.dovecot.org/configuration_manual/authentication/dict/#complete-example-for-authenticating-via-a-unix-socket)
  to authenticate logins. 

- [`filtermail`](https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/filtermail.py) 
  prevents unencrypted email from leaving or entering the chatmail service
  and is integrated into Postfix's outbound and inbound mail pipelines.

- [`chatmail-metadata`](https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/metadata.py) is contacted by a
  [Dovecot lua script](https://github.com/chatmail/relay/blob/main/cmdeploy/src/cmdeploy/dovecot/push_notification.lua)
  to store user-specific relay-side config.
  On new messages,
  it [passes the user's push notification token](https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/notifier.py)
  to [notifications.delta.chat](https://delta.chat/help#instant-delivery)
  so the push notifications on the user's phone can be triggered
  by Apple/Google/Huawei.

- [`delete_inactive_users`](https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/delete_inactive_users.py)
  deletes users if they have not logged in for a very long time.
  The timeframe can be configured in `chatmail.ini`.

- [`lastlogin`](https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/lastlogin.py)
  is contacted by Dovecot when a user logs in
  and stores the date of the login.

- [`echobot`](https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/echo.py)
  is a small bot for test purposes.
  It simply echoes back messages from users.

- [`chatmail-metrics`](https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/metrics.py)
  collects some metrics and displays them at `https://example.org/metrics`.

### Home page and getting started for users

`cmdeploy run` also creates default static web pages and deploys them
to a Nginx web server with:

- a default `index.html` along with a QR code that users can click to
  create an address on your chatmail relay 

- a default `info.html` that is linked from the home page

- a default `policy.html` that is linked from the home page

All `.html` files are generated
by the according markdown `.md` file in the `www/src` directory.


### Refining the web pages

```
scripts/cmdeploy webdev
```

This starts a local live development cycle for chatmail web pages:

- uses the `www/src/page-layout.html` file for producing static
  HTML pages from `www/src/*.md` files

- continously builds the web presence reading files from `www/src` directory
  and generating HTML files and copying assets to the `www/build` directory.

- Starts a browser window automatically where you can "refresh" as needed.

## Mailbox directory layout

Fresh chatmail addresses have a mailbox directory that contains: 

- a `password` file with the salted password required for authenticating
  whether a login may use the address to send/receive messages. 
  If you modify the password file manually, you effectively block the user. 

- `enforceE2EEincoming` is a default-created file with each address. 
  If present the file indicates that this chatmail address rejects incoming cleartext messages.
  If absent the address accepts incoming cleartext messages. 

- `dovecot*`, `cur`, `new` and `tmp` represent IMAP/mailbox state. 
  If the address is only used by one device, the Maildir directories
  will typically be empty unless the user of that address hasn't been online 
  for a while. 


## Emergency Commands to disable automatic address creation

If you need to stop address creation,
e.g. because some script is wildly creating addresses, 
login with ssh and run:

```
    touch /etc/chatmail-nocreate
```

Chatmail address creation will be denied while this file is present.

### Ports

[Postfix](http://www.postfix.org/) listens on ports 25 (SMTP) and 587 (SUBMISSION) and 465 (SUBMISSIONS).
[Dovecot](https://www.dovecot.org/) listens on ports 143 (IMAP) and 993 (IMAPS).
[Nginx](https://www.nginx.com/) listens on port 8443 (HTTPS-ALT) and 443 (HTTPS).
Port 443 multiplexes HTTPS, IMAP and SMTP using ALPN to redirect connections to ports 8443, 465 or 993.
[acmetool](https://hlandau.github.io/acmetool/) listens on port 80 (HTTP).

chatmail-core based apps will, however, discover all ports and configurations
automatically by reading the [autoconfig XML file](https://www.ietf.org/archive/id/draft-bucksch-autoconfig-00.html) from the chatmail relay server.

## Email authentication

Chatmail relays enforce [DKIM](https://www.rfc-editor.org/rfc/rfc6376)
to authenticate incoming emails.
Incoming emails must have a valid DKIM signature with
Signing Domain Identifier (SDID, `d=` parameter in the DKIM-Signature header)
equal to the `From:` header domain.
This property is checked by OpenDKIM screen policy script
before validating the signatures.
This correpsonds to strict [DMARC](https://www.rfc-editor.org/rfc/rfc7489) alignment (`adkim=s`),
but chatmail does not rely on DMARC and does not consult the sender policy published in DMARC records.
Other legacy authentication mechanisms such as [iprev](https://www.rfc-editor.org/rfc/rfc8601#section-2.7.3)
and [SPF](https://www.rfc-editor.org/rfc/rfc7208) are also not taken into account.
If there is no valid DKIM signature on the incoming email,
the sender receives a "5.7.1 No valid DKIM signature found" error.

Outgoing emails must be sent over authenticated connection
with envelope MAIL FROM (return path) corresponding to the login.
This is ensured by Postfix which maps login username
to MAIL FROM with
[`smtpd_sender_login_maps`](https://www.postfix.org/postconf.5.html#smtpd_sender_login_maps)
and rejects incorrectly authenticated emails with [`reject_sender_login_mismatch`](reject_sender_login_mismatch) policy.
`From:` header must correspond to envelope MAIL FROM,
this is ensured by `filtermail` proxy.

## TLS requirements

Postfix is configured to require valid TLS
by setting [`smtp_tls_security_level`](https://www.postfix.org/postconf.5.html#smtp_tls_security_level) to `verify`.
If emails don't arrive at your chatmail relay server, 
the problem is likely that your relay does not have a valid TLS certificate.

You can test it by resolving `MX` records of your relay domain
and then connecting to MX relays (e.g `mx.example.org`) with
`openssl s_client -connect mx.example.org:25 -verify_hostname mx.example.org -verify_return_error -starttls smtp`
from the host that has open port 25 to verify that certificate is valid.

When providing a TLS certificate to your chatmail relay server, 
make sure to provide the full certificate chain
and not just the last certificate.

If you are running an Exim server and don't see incoming connections
from a chatmail relay server in the logs,
make sure `smtp_no_mail` log item is enabled in the config
with `log_selector = +smtp_no_mail`.
By default Exim does not log sessions that are closed
before sending the `MAIL` command.
This happens if certificate is not recognized as valid by Postfix,
so you might think that connection is not established
while actually it is a problem with your TLS certificate.

## Migrating a chatmail relay to a new host

If you want to migrate chatmail relay from an old machine
to a new machine,
you can use these steps.
They were tested with a Linux laptop;
you might need to adjust some of the steps to your environment.

Let's assume that your `mail_domain` is `mail.example.org`,
all involved machines run Debian 12,
your old site's IP address is `13.37.13.37`,
and your new site's IP address is `13.12.23.42`.

Note, you should lower the TTLs of your DNS records to a value
such as 300 (5 minutes) so the migration happens as smoothly as possible.

During the guide you might get a warning about changed SSH Host keys;
in this case, just run `ssh-keygen -R "mail.example.org"` as recommended.

1. First, disable mail services on the old site. 

   ```
    cmdeploy run --disable-mail --ssh-host 13.37.13.37
   ```

   Now your users will notice the migration
   and will not be able to send or receive messages
   until the migration is completed.

2. Now we want to copy `/home/vmail`, `/var/lib/acme`, `/etc/dkimkeys`, `/run/echobot`, and `/var/spool/postfix` to the new site. 
   Login to the old site while forwarding your SSH agent 
   so you can copy directly from the old to the new site with your SSH key:
   ```
    ssh -A root@13.37.13.37
    tar c - /home/vmail/mail /var/lib/acme /etc/dkimkeys /run/echobot /var/spool/postfix | ssh root@13.12.23.42 "tar x -C /"
   ```

   This transfers all addresses, the TLS certificate, DKIM keys (so DKIM DNS record remains valid), and the echobot's password so it continues to function.
   It also preserves the Postfix mail spool so any messages pending delivery will still be delivered.

3. Install chatmail on the new machine:

   ```
    cmdeploy run --disable-mail --ssh-host 13.12.23.42
   ```
   Postfix and Dovecot are disabled for now; we will enable them later. 
   We first need to make the new site fully operational. 

3. On the new site, run the following to ensure the ownership is correct in case UIDs/GIDs changed:

   ```
    chown root: -R /var/lib/acme
    chown opendkim: -R /etc/dkimkeys
    chown vmail: -R /home/vmail/mail
    chown echobot: -R /run/echobot
   ```

4. Now, update DNS entries. 

   If other MTAs try to deliver messages to your chatmail domain they may fail intermittently,
   as DNS catches up with the new site settings 
   but normally will retry delivering messages
   for at least a week, so messages will not be lost.

5. Finally, you can execute `cmdeploy run --ssh-host 13.12.23.42` to turn on chatmail on the new relay.
   Your users will be able to use the chatmail relay as soon as the DNS changes have propagated.
   Voilà!

## Setting up a reverse proxy

A chatmail relay MTA does not track or depend on the client IP address
for its operation, so it can be run behind a reverse proxy.
This will not even affect incoming mail authentication
as DKIM only checks the cryptographic signature
of the message and does not use the IP address as the input.

For example, you may want to self-host your chatmail relay
and only use hosted VPS to provide a public IP address
for client connections and incoming mail.
You can connect chatmail relay to VPS
using a tunnel protocol
such as [WireGuard](https://www.wireguard.com/)
and setup a reverse proxy on a VPS
to forward connections to the chatmail relay
over the tunnel.
You can also setup multiple reverse proxies
for your chatmail relay in different networks
to ensure your relay is reachable even when
one of the IPs becomes inaccessible due to
hosting or routing problems.

Note that your chatmail relay still needs
to be able to make outgoing connections on port 25
to send messages outside.

To setup a reverse proxy
(or rather Destination NAT, DNAT)
for your chatmail relay,
put the following configuration in `/etc/nftables.conf`:
```
#!/usr/sbin/nft -f

flush ruleset

define wan = eth0

# Which ports to proxy.
#
# Note that SSH is not proxied
# so it is possible to log into the proxy server 
# and not the original one.
define ports = { smtp, http, https, imap, imaps, submission, submissions }

# The host we want to proxy to.
define ipv4_address = AAA.BBB.CCC.DDD
define ipv6_address = [XXX::1]

table ip nat {
        chain prerouting {
                type nat hook prerouting priority dstnat; policy accept;
                iif $wan tcp dport $ports dnat to $ipv4_address
        }

        chain postrouting {
                type nat hook postrouting priority 0;

                oifname $wan masquerade
        }
}

table ip6 nat {
        chain prerouting {
                type nat hook prerouting priority dstnat; policy accept;
                iif $wan tcp dport $ports dnat to $ipv6_address
        }

        chain postrouting {
                type nat hook postrouting priority 0;

                oifname $wan masquerade
        }
}

table inet filter {
        chain input {
                type filter hook input priority filter; policy drop;

                # Accept ICMP.
                # It is especially important to accept ICMPv6 ND messages,
                # otherwise IPv6 connectivity breaks.
                icmp type { echo-request } accept
                icmpv6 type { echo-request, nd-neighbor-solicit, nd-router-advert, nd-neighbor-advert } accept

                # Allow incoming SSH connections.
                tcp dport { ssh } accept

                ct state established accept
        }
        chain forward {
                type filter hook forward priority filter; policy drop;

                ct state established accept
                ip daddr $ipv4_address counter accept
                ip6 daddr $ipv6_address counter accept
        }
        chain output {
                type filter hook output priority filter;
        }
}
```

Run `systemctl enable nftables.service`
to ensure configuration is reloaded when the proxy relay reboots.

Uncomment in `/etc/sysctl.conf` the following two lines:

```
net.ipv4.ip_forward=1
net.ipv6.conf.all.forwarding=1
```

Then reboot the relay or do `sysctl -p` and `nft -f /etc/nftables.conf`.

Once proxy relay is set up,
you can add its IP address to the DNS.

## Neighbors and Acquaintances

Here are some related projects that you may be interested in:

- [Mox](https://github.com/mjl-/mox): A Golang email server.  [Work is in
  progress](https://github.com/mjl-/mox/issues/251) to modify it to support all
  of the features and configuration settings required to operate as a chatmail
  relay.
