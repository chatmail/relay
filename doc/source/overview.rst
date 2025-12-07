
Technical overview
======================


Directories of the relay repository
-----------------------------------

The `chatmail relay repository <https://github.com/chatmail/relay/tree/main/>`_
has four main directories.

``scripts/``
~~~~~~~~~~~~~

`scripts <https://github.com/chatmail/relay/tree/main/scripts>`_
offers two convenience tools for beginners:

- ``initenv.sh`` installs a local virtualenv Python environment and
  installs necessary dependencies

- ``scripts/cmdeploy`` script enables you to run the ``cmdeploy``
  command line tool in the local Python virtual environment.


``cmdeploy/``
~~~~~~~~~~~~~

The ``cmdeploy`` directory contains the Python package and command line tool
to setup a chatmail relay remotely via SSH:

- ``cmdeploy init`` creates the ``chatmail.ini`` config file locally.

- ``cmdeploy run`` under the hood uses pyinfra_
  to automatically install or upgrade all chatmail components on a relay,
  according to the local ``chatmail.ini`` config.

The deployed system components of a chatmail relay are:

-  Postfix_ is the Mail Transport Agent (MTA) and
   accepts messages from, and sends messages to, the wider email MTA network

-  Dovecot_ is the Mail Delivery Agent (MDA) and
   stores messages for users until they download them

-  Nginx_ shows the web page with privacy policy and additional information

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


``chatmaild/``
~~~~~~~~~~~~~~

`chatmaild <https://github.com/chatmail/relay/tree/main/chatmaild>`_
is a Python package containing several small services which handle
authentication, trigger push notifications on new messages, ensure
that outbound mails are encrypted, delete inactive users, and some
other minor things. chatmaild can also be installed as a stand-alone
Python package.

``chatmaild`` implements various systemd-controlled services
that integrate with Dovecot and Postfix to achieve instant-onboarding
and only relaying OpenPGP end-to-end messages encrypted messages. A
short overview of ``chatmaild`` services:

-  `doveauth <https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/doveauth.py>`_
   implements create-on-login address semantics and is used by Dovecot
   during IMAP login and by Postfix during SMTP/SUBMISSION login which
   in turn uses `Dovecot SASL
   <https://doc.dovecot.org/2.3/configuration_manual/authentication/dict/#complete-example-for-authenticating-via-a-unix-socket>`_
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
   `notifications.delta.chat <https://delta.chat/en/help#instant-delivery>`_
   so the push notifications on the user’s phone can be triggered by
   Apple/Google/Huawei.

-  `chatmail-expire <https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/expire.py>`_
   deletes users if they have not logged in for a longer while.
   The timeframe can be configured in ``chatmail.ini``.

-  `lastlogin <https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/lastlogin.py>`_
   is contacted by Dovecot when a user logs in and stores the date of
   the login.

-  `metrics <https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/metrics.py>`_
   collects some metrics and displays them at
   ``https://example.org/metrics``.

``www/``
~~~~~~~~~

`www <https://github.com/chatmail/relay/tree/main/www>`_ contains
the html, css, and markdown files which make up a chatmail relay’s
web page. Edit them before deploying to make your chatmail relay
stand out.


Chatmail relay dependency diagram
---------------------------------

.. mermaid::
   :caption: This diagram shows relay components and dependencies/communication paths.

    graph LR;
        letsencrypt --- |80|acmetool-redirector;
        acmetool-redirector --- |443|nginx-right(["`nginx
        (external)`"]);
        nginx-external --- |465|postfix;
        nginx-external(["`nginx
        (external)`"]) --- |8443|nginx-internal["`nginx
        (internal)`"];
        nginx-internal --- website["`Website
        /var/www/html`"];
        nginx-internal --- newemail.py;
        nginx-internal --- autoconfig.xml;
        certs-nginx[("`TLS certs
        /var/lib/acme`")] --> nginx-internal;
        systemd-timer --- chatmail-metrics;
        systemd-timer --- acmetool;
        systemd-timer --- chatmail-expire-daily;
        systemd-timer --- chatmail-fsreport-daily;
        chatmail-metrics --- website;
        acmetool --> certs[("`TLS certs
        /var/lib/acme`")];
        nginx-external --- |993|dovecot;
        postfix --- |SASL|dovecot;
        autoconfig.xml --- postfix;
        autoconfig.xml --- dovecot;
        postfix --- |10080|filtermail-outgoing;
        postfix --- |10081|filtermail-incoming;
        filtermail-outgoing --- |10025 reinject|postfix;
        filtermail-incoming --- |10026 reinject|postfix;
        dovecot --- |doveauth.socket|doveauth;
        dovecot --- |message delivery|maildir["maildir
        /home/vmail/.../user"];
        dovecot --- |lastlogin.socket|lastlogin;
        dovecot --- chatmail-metadata;
        lastlogin --- maildir;
        doveauth --- maildir;
        chatmail-expire-daily --- maildir;
        chatmail-fsreport-daily --- maildir;
        chatmail-metadata --- iroh-relay;
        chatmail-metadata --- |encrypted device token| notifications.delta.chat;
        certs-nginx --> postfix;
        certs-nginx --> dovecot;
        style certs fill:#ff6;
        style website fill:#ff6;
        style maildir fill:#ff6;
        style certs-nginx fill:#ff6;
        style nginx-external fill:#f66;
        style nginx-right fill:#f66;
        style postfix fill:#f66;
        style dovecot fill:#f66;
        style notification-proxy fill:#f66;

Message between users on the same relay
---------------------------------------

.. mermaid::
    :caption: This diagram shows the path a non-federated message takes.

    graph LR;
        sender --> |465|smtps/smtpd;
        sender --> |587|submission/smtpd;
        smtps/smtpd --> |10080|filtermail;
        submission/smtpd --> |10080|filtermail;
        filtermail --> |10025|smtpd_reinject;
        smtpd_reinject --> cleanup;
        cleanup --> qmgr;
        qmgr --> smtpd_accepts_message;
        qmgr --> |lmtp|dovecot;
        dovecot --> recipient;
        dovecot --> sender's_other_devices;

Operational details of a chatmail relay
----------------------------------------

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

Postfix_ listens on ports

- 25 (SMTP)

- 587 (SUBMISSION) and

- 465 (SUBMISSIONS)

Dovecot_ listens on ports

- 143 (IMAP) and

- 993 (IMAPS)

Nginx_ listens on port

- 8443 (HTTPS-ALT) and

- 443 (HTTPS) which multiplexes HTTPS, IMAP and SMTP using ALPN
  to redirect connections to ports 8443, 465 or 993.

`acmetool <https://hlandau.github.io/acmetool/>`_ listens on port:

- 80 (HTTP).

`chatmail-turn <https://github.com/chatmail/chatmail-turn>`_ listens on port

- 3478 UDP (STUN/TURN), and temporarily opens further UDP ports
  when users request them. UDP port range is not restricted, any free port
  may be allocated.

chatmail-core based apps will, however, discover all ports and
configurations automatically by reading the `autoconfig XML
file <https://www.ietf.org/archive/id/draft-bucksch-autoconfig-00.html>`_
from the chatmail relay server.

Email domain authentication (DKIM)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Chatmail relays enforce :rfc:`DKIM <6376>` to authenticate incoming emails.
Incoming emails must have a valid DKIM signature with
Signing Domain Identifier (SDID, ``d=`` parameter in the DKIM-Signature
header) equal to the ``From:`` header domain. This property is checked
by OpenDKIM screen policy script before validating the signatures. This
corresponds to strict :rfc:`DMARC <7489>` alignment (``adkim=s``).
If there is no valid DKIM signature on the incoming email, the
sender receives a “5.7.1 No valid DKIM signature found” error.
After validating the DKIM signature,
the `final.lua` script strips all ``OpenDKIM:`` headers to reduce message size on disc.

Note that chatmail relays

- do **not** rely on DMARC and do not consult the sender policy published in DMARC records;

- do **not** rely on legacy authentication mechanisms such as
  :rfc:`iprev <8601#section-2.7.3>` and :rfc:`SPF <7208>`.
  Any IP address is accepted if the DKIM signature was valid.

Outgoing emails must be sent over authenticated connection with envelope
``MAIL FROM`` (return path) corresponding to the login.
This is ensured by Postfix which maps login username to ``MAIL FROM`` with
`smtpd_sender_login_maps <https://www.postfix.org/postconf.5.html#smtpd_sender_login_maps>`_
and rejects incorrectly authenticated emails with
`reject_sender_login_mismatch <https://www.postfix.org/postconf.5.html#reject_sender_login_mismatch>`_ policy.
``From:`` header must correspond to envelope ``MAIL FROM``, this is
ensured by ``filtermail`` proxy.

TLS requirements
~~~~~~~~~~~~~~~~

Postfix is configured to require valid TLS by setting
`smtp_tls_security_level <https://www.postfix.org/postconf.5.html#smtp_tls_security_level>`_
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


.. _dovecot: https://dovecot.org
.. _postfix: https://www.postfix.org
.. _nginx: https://nginx.org
.. _pyinfra: https://pyinfra.com


Architecture of cmdeploy
------------------------

cmdeploy is a Python program that uses the pyinfra library to deploy
chatmail relays, with all the necessary software, configuration, and
services.  The deployment process performs three primary types of
operation:

1. Installation of software, universal across all deployments.
2. Configuration of software, with deploy-specific variations.
3. Activation of services.

The process is implemented through a family of "deployer" objects
which all derive from a common ``Deployer`` base class, defined in
cmdeploy/src/cmdeploy/deployer.py.  Each object provides
implementation methods for the three stages -- install, configure, and
activate.  The top-level procedure in ``deploy_chatmail()`` calls
these methods for all the deployer objects, via the
``Deployment.perform_stages()`` method, also defined in deployer.py.
This first calls all the install methods, then the configure methods,
then the activate methods.

The ``Deployment`` class also implements support for a CMDEPLOY_STAGES
environment variable, which allows limiting the process to specific
stages.  Note that some deployers are stateful between the stages
(this is one reason why they are implemented as objects), and that
state will not get propagated between stages when run in separate
invocations of cmdeploy.  This environment variable is intended for
use in future revisions to support building Docker images with
software pre-installed, and configuration of containers at run time
from environment variables.

The, ``install()`` methods for the deployer classes should use 'self'
as little as possible, preferably not at all.  In particular,
``install()`` methods should never depend on "config" data, such as
the config dictionary in ``self.config`` or specific values like
``self.mail_domain``.  This ensures that these methods can be used to
perform generic installation operations that are applicable across
multiple relay deployments, and therefore can be called in the process
of building a general-purpose container image.

Operations that start services for systemd-based deployments should
only be called from the ``activate_impl()`` methods.  These methods
will not be called in non-systemd container environments.
