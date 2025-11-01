
Services and internal structure
-------------------------------

The chatmail relay repository has four directories:

-  `cmdeploy <https://github.com/chatmail/relay/tree/main/cmdeploy>`_
   is a collection of configuration files and a
   `pyinfra <https://pyinfra.com>`_ - based deployment script.

-  `chatmaild <https://github.com/chatmail/relay/tree/main/chatmaild>`_
   is a Python package containing several small services which handle
   authentication, trigger push notifications on new messages, ensure
   that outbound mails are encrypted, delete inactive users, and some
   other minor things. chatmaild can also be installed as a stand-alone
   Python package.

-  `www <https://github.com/chatmail/relay/tree/main/www>`_ contains
   the html, css, and markdown files which make up a chatmail relay’s
   web page. Edit them before deploying to make your chatmail relay
   stand out.

-  `scripts <https://github.com/chatmail/relay/tree/main/scripts>`_
   offers two convenience tools for beginners; ``initenv.sh`` installs
   the necessary dependencies to a local virtual environment, and the
   ``scripts/cmdeploy`` script enables you to run the ``cmdeploy``
   command line tool in the local virtual environment.

cmdeploy
~~~~~~~~

The ``cmdeploy/src/cmdeploy/cmdeploy.py`` command line tool helps with
setting up and managing the chatmail service. ``cmdeploy init`` creates
the ``chatmail.ini`` config file. ``cmdeploy run`` uses a
`pyinfra <https://pyinfra.com/>`_-based
`script <cmdeploy/src/cmdeploy/__init__.py>`_ to automatically
install or upgrade all chatmail components on a relay, according to the
``chatmail.ini`` config.

The components of chatmail are:

-  `Postfix SMTP MTA <https://www.postfix.org>`_ accepts and relays
   messages (both from your users and from the wider e-mail MTA network)

-  `Dovecot IMAP MDA <https://www.dovecot.org>`_ stores messages for
   your users until they download them

-  `Nginx <https://nginx.org/>`_ shows the web page with your privacy
   policy and additional information

-  `acmetool <https://hlandau.github.io/acmetool/>`_ manages TLS
   certificates for Dovecot, Postfix, and Nginx

-  `OpenDKIM <http://www.opendkim.org/>`_ for signing messages with
   DKIM and rejecting inbound messages without DKIM

-  `mtail <https://google.github.io/mtail/>`_ for collecting anonymized
   metrics in case you have monitoring

-  `Iroh relay <https://www.iroh.computer/docs/concepts/relay>`_ which
   helps client devices to establish Peer-to-Peer connections

-  `TURN <https://github.com/chatmail/chatmail-turn>`_ to enable relay
   users to start webRTC calls even if a p2p connection can’t be
   established

-  and the chatmaild services, explained in the next section:



chatmaild
~~~~~~~~~

``chatmaild`` implements various systemd-controlled services
that integrate with Dovecot and Postfix to achieve instant-onboarding
and only relaying OpenPGP end-to-end messages encrypted messages. A
short overview of ``chatmaild`` services:

-  `doveauth <https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/doveauth.py>`_
   implements create-on-login address semantics and is used by Dovecot
   during IMAP login and by Postfix during SMTP/SUBMISSION login which
   in turn uses `Dovecot
   SASL <https://doc.dovecot.org/configuration_manual/authentication/dict/#complete-example-for-authenticating-via-a-unix-socket>`_
   to authenticate logins.

-  `filtermail <https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/filtermail.py>`_
   prevents unencrypted email from leaving or entering the chatmail
   service and is integrated into Postfix’s outbound and inbound mail
   pipelines.

-  `chatmail-metadata <https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/metadata.py>`_
   is contacted by a `Dovecot lua
   script <https://github.com/chatmail/relay/blob/main/cmdeploy/src/cmdeploy/dovecot/push_notification.lua>`_
   to store user-specific relay-side config. On new messages, it `passes
   the user’s push notification
   token <https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/notifier.py>`_
   to
   `notifications.delta.chat <https://delta.chat/help#instant-delivery>`_
   so the push notifications on the user’s phone can be triggered by
   Apple/Google/Huawei.

-  `delete_inactive_users <https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/delete_inactive_users.py>`_
   deletes users if they have not logged in for a very long time. The
   timeframe can be configured in ``chatmail.ini``.

-  `lastlogin <https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/lastlogin.py>`_
   is contacted by Dovecot when a user logs in and stores the date of
   the login.

-  `echobot <https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/echo.py>`_
   is a small bot for test purposes. It simply echoes back messages from
   users.

-  `metrics <https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/metrics.py>`_
   collects some metrics and displays them at
   ``https://example.org/metrics``.


Mailbox directory layout
~~~~~~~~~~~~~~~~~~~~~~~~

Fresh chatmail addresses have a mailbox directory that contains:

-  a ``password`` file with the salted password required for
   authenticating whether a login may use the address to send/receive
   messages. If you modify the password file manually, you effectively
   block the user.

-  ``enforceE2EEincoming`` is a default-created file with each address.
   If present the file indicates that this chatmail address rejects
   incoming cleartext messages. If absent the address accepts incoming
   cleartext messages.

-  ``dovecot*``, ``cur``, ``new`` and ``tmp`` represent IMAP/mailbox
   state. If the address is only used by one device, the Maildir
   directories will typically be empty unless the user of that address
   hasn’t been online for a while.

Active ports
~~~~~~~~~~~~

`Postfix <http://www.postfix.org/>`_ listens on ports 25 (SMTP) and 587
(SUBMISSION) and 465 (SUBMISSIONS).
`Dovecot <https://www.dovecot.org/>`_ listens on ports 143 (IMAP) and
993 (IMAPS). `Nginx <https://www.nginx.com/>`_ listens on port 8443
(HTTPS-ALT) and 443 (HTTPS). Port 443 multiplexes HTTPS, IMAP and SMTP
using ALPN to redirect connections to ports 8443, 465 or 993.
`acmetool <https://hlandau.github.io/acmetool/>`_ listens on port 80
(HTTP). `chatmail-turn <https://github.com/chatmail/chatmail-turn>`_
listens on UDP port 3478 (STUN/TURN), and temporarily opens UDP ports
when users request them. UDP port range is not restricted, any free port
may be allocated.

chatmail-core based apps will, however, discover all ports and
configurations automatically by reading the `autoconfig XML
file <https://www.ietf.org/archive/id/draft-bucksch-autoconfig-00.html>`_
from the chatmail relay server.

Email authentication
~~~~~~~~~~~~~~~~~~~~

Chatmail relays enforce
`DKIM <https://www.rfc-editor.org/rfc/rfc6376>`_ to authenticate
incoming emails. Incoming emails must have a valid DKIM signature with
Signing Domain Identifier (SDID, ``d=`` parameter in the DKIM-Signature
header) equal to the ``From:`` header domain. This property is checked
by OpenDKIM screen policy script before validating the signatures. This
correpsonds to strict `DMARC <https://www.rfc-editor.org/rfc/rfc7489>`_
alignment (``adkim=s``), but chatmail does not rely on DMARC and does
not consult the sender policy published in DMARC records. Other legacy
authentication mechanisms such as
`iprev <https://www.rfc-editor.org/rfc/rfc8601#section-2.7.3>`_ and
`SPF <https://www.rfc-editor.org/rfc/rfc7208>`_ are also not taken into
account. If there is no valid DKIM signature on the incoming email, the
sender receives a “5.7.1 No valid DKIM signature found” error.

Outgoing emails must be sent over authenticated connection with envelope
MAIL FROM (return path) corresponding to the login. This is ensured by
Postfix which maps login username to MAIL FROM with
```smtpd_sender_login_maps`` <https://www.postfix.org/postconf.5.html#smtpd_sender_login_maps>`_
and rejects incorrectly authenticated emails with
```reject_sender_login_mismatch`` <reject_sender_login_mismatch>`_
policy. ``From:`` header must correspond to envelope MAIL FROM, this is
ensured by ``filtermail`` proxy.

TLS requirements
~~~~~~~~~~~~~~~~

Postfix is configured to require valid TLS by setting
```smtp_tls_security_level`` <https://www.postfix.org/postconf.5.html#smtp_tls_security_level>`_
to ``verify``. If emails don’t arrive at your chatmail relay server, the
problem is likely that your relay does not have a valid TLS certificate.

You can test it by resolving ``MX`` records of your relay domain and
then connecting to MX relays (e.g ``mx.example.org``) with
``openssl s_client -connect mx.example.org:25 -verify_hostname mx.example.org -verify_return_error -starttls smtp``
from the host that has open port 25 to verify that certificate is valid.

When providing a TLS certificate to your chatmail relay server, make
sure to provide the full certificate chain and not just the last
certificate.

If you are running an Exim server and don’t see incoming connections
from a chatmail relay server in the logs, make sure ``smtp_no_mail`` log
item is enabled in the config with ``log_selector = +smtp_no_mail``. By
default Exim does not log sessions that are closed before sending the
``MAIL`` command. This happens if certificate is not recognized as valid
by Postfix, so you might think that connection is not established while
actually it is a problem with your TLS certificate.
