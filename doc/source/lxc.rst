Local testing with LXC/Incus
============================

.. warning::

   cmdeploy LXC support is geared towards local testing and CI, only.
   Do not base production setups on it.


The ``cmdeploy`` tool includes support for running
chatmail relays inside local
`Incus <https://linuxcontainers.org/incus/>`_ LXC containers.
This is useful for development, testing, and CI
without requiring a remote server.
LXC system containers behave like lightweight virtual machines.
They share the host's kernel but run their own init system
(systemd), package manager, and network stack,
so the cmdeploy deployment scripts work exactly
as they would on a real Debian server or cloud VPS.

Prerequisites
-------------

Install `Incus <https://linuxcontainers.org/incus/>`_
(LXC container manager).
See the `official installation guide
<https://linuxcontainers.org/incus/docs/main/installing/>`_
for full details.

After installing incus, initialise and grant yourself access::

    sudo incus admin init --minimal
    sudo usermod -aG incus-admin $USER

.. warning::

   You **must now log out and back in** (or run ``newgrp incus-admin``)
   after adding yourself to the group.
   Without this, all ``cmdeploy lxc-*`` commands
   will fail with permission errors.

Verify the installation works by running ``incus list``,
which should print an empty table without errors.


Quick start
-----------

::

    cd relay
    scripts/initenv.sh               # bootstrap venv
    source venv/bin/activate         # activate venv
    cmdeploy lxc-test                # create containers, deploy, test


The ``lxc-test`` command executes each ``cmdeploy`` subprocess command
so you can copy-paste and run them individually.
No host DNS delegation or ``~/.ssh/config`` changes are needed
because lxc-test passes ssh-related CLI options to "cmdeploy run" and "cmdeploy test" commands.


CLI reference
--------------

``lxc-start [--ipv4-only] [--run] [NAME ...]``
    Create and start containers.
    Without arguments, creates ``test0-localchat`` and ``ns-localchat`` (DNS).
    Pass one or more ``NAME`` arguments to create user relay containers instead
    (e.g. ``cmdeploy lxc-start myrelay``).
    Use ``--ipv4-only`` to set ``disable_ipv6 = True`` in the generated ``chatmail.ini``,
    producing an IPv4-only relay.
    Use ``--run`` to automatically run ``cmdeploy run`` on each container after starting it.
    Generates ``lxconfigs/ssh-config``.
    It reuses existing containers and resets DNS zones to minimal records.

``lxc-stop [--destroy] [--destroy-all] [NAME ...]``
    Stop relay containers.
    Without arguments, stops ``test0-localchat`` and ``test1-localchat``.
    Pass ``NAME`` to stop specific containers.
    Use ``--destroy`` to also delete the containers and their config files.
    Use ``--destroy-all`` to additionally destroy
    the ``ns-localchat`` DNS container **and** remove
    the cached ``localchat-base`` and ``localchat-relay``
    images, giving a fully clean slate for the next ``lxc-test``.
    User containers are **never** destroyed unless named explicitly.

``lxc-test [--one]``
    Idempotent full pipeline:

    1. ``lxc-start``: create ``test0`` + ``test1``
       containers, minimal DNS

    2. ``cmdeploy run``: deploy chatmail services on each relay

    3. locally cache ``localchat-relay`` image after first successful deploy

    4. ``cmdeploy dns --zonefile``: generate standard
       BIND-format zone files, load full DNS records

    5. ``cmdeploy test``: run full test suite

    By default creates, deploys, and tests both ``test0`` and ``test1``
    for dual-domain federation testing (sets ``CHATMAIL_DOMAIN2=_test1.localchat``).
    test0 runs dual-stack (IPv4 + IPv6) while test1 runs IPv4-only (``disable_ipv6 = True``).
    Pass ``--one`` to only deploy and test against ``test0``
    (skips ``test1``, does not set ``CHATMAIL_DOMAIN2``).

``lxc-status``
    Show live status of all LXC containers (including the DNS container),
    deploy freshness (comparing ``/etc/chatmail-version``
    against local ``git rev-parse HEAD`` and ``git diff``),
    SSH config inclusion, and host DNS forwarding for ``.localchat``.
    Reports **IN-SYNC**, **DIRTY** (hash matches but uncommitted changes exist),
    **STALE** (different commit), or **NOT DEPLOYED**.


Container types
-----------------

**Test relay containers** (``test0-localchat``, ``test1-localchat``)
    Created automatically by ``lxc-test``.
    **test0** has IPv4 and IPv6 configured,
    **test1** is IPv4-only (``disable_ipv6 = True``).

**User relay containers** (``<name>-localchat``)
    Created by ``cmdeploy lxc-start <name>``
    where ``<name>`` does not start with ``test``.
    These are personal development instances,
    never touched by ``lxc-stop --destroy`` unless named explicitly.

**DNS container** (``ns-localchat``)
    Singleton container running PowerDNS.
    Created automatically when any relay is started.


.. _lxc-ssh-config:

SSH configuration
-----------------

``cmdeploy lxc-start`` generates ``lxconfigs/ssh-config``,
a standard OpenSSH config file mapping every container name,
its domain, and a short alias to the container's IP address::

    Host test0-localchat _test0.localchat _test0
        Hostname 10.204.0.42
        User root
        IdentityFile /path/to/relay/lxconfigs/id_localchat
        IdentitiesOnly yes
        StrictHostKeyChecking accept-new
        UserKnownHostsFile /dev/null
        LogLevel ERROR

All ``cmdeploy`` commands (``run``, ``dns``, ``status``, ``test``)
accept ``--ssh-config lxconfigs/ssh-config`` to use this file.
``lxc-test`` passes it automatically.

**Using containers from the host shell:**

To make ``ssh _test0`` work from any terminal, add one line to ``~/.ssh/config``::

    Include /absolute/path/to/relay/lxconfigs/ssh-config


.. _lxc-dns-setup:
.. _localchat-tld:

``.localchat`` DNS and name resolution
---------------------------------------

All LXC-managed chatmail domains use the ``.localchat`` pseudo-TLD
(e.g. ``_test0.localchat``, ``_test1.localchat``),
a non-delegated suffix that exists only within the local PowerDNS infrastructure.
A dedicated DNS container (``ns-localchat``)
is created so that local test relays interact
with DNS similar to a regular public Internet setup.
On first start, ``cmdeploy lxc-start`` creates this container
running two `PowerDNS <https://www.powerdns.com/>`_ services:

* **pdns-server** (authoritative) serves ``.localchat``
  zones from a local SQLite database.

* **pdns-recursor** (recursive) listens on the Incus
  bridge so all containers can use it.
  Forwards ``.localchat`` queries to the local
  authoritative server and everything else to Quad9 (``9.9.9.9``).

After the DNS container is up, ``lxc-start`` configures the Incus bridge
to advertise its IP via DHCP and disables Incus's own DNS.
DNS records are then created in two phases matching the "cmdeploy run" deployment flow:

1. **``lxc-start``** resets each relay zone to
   **SOA, NS, and A** records (plus **AAAA** for dual-stack containers).
   If host DNS resolution is configured, users can
   afterwards run ``cmdeploy run --config lxconfigs/chatmail-test0.ini
   --ssh-config lxconfigs/ssh-config --ssh-host _test0.localchat``.
   LXC subcommands do not depend on host DNS resolution
   and resolve addresses via ``lxconfigs/ssh-config``.

2. **``cmdeploy dns --zonefile``** generates a standard
   BIND-format zone file (MX, TXT/SPF, TXT/DMARC,
   TXT/MTA-STS, SRV, CNAME, DKIM) and loads it
   into PowerDNS.

This two-phase approach prevents premature configuration of mail records
before the relay is actually deployed and running.
Once ``cmdeploy run`` deploys `Unbound <https://nlnetlabs.nl/projects/unbound/>`_
inside a relay container, Unbound has a configuration plugin snippet
that forwards all ``.localchat`` queries to the PowerDNS recursor,
and lets all other queries go through normal recursive resolution.


State outside the repository
-----------------------------

All generated configuration by lxc subcommands live in ``lxconfigs/``
(git-ignored), including the SSH key pair (``id_localchat``),
per-container ``chatmail-*.ini`` files, zone files, and ``ssh-config``.

The only state *outside* the repository is the Incus containers and images themselves
(managed via the ``incus`` CLI, labelled with ``user.localchat-managed=true``).
The Incus image store retains the following snapshot images:

* ``localchat-base``: Debian 12 with openssh-server and Python (built on first run)

* ``localchat-relay``: fully deployed relay snapshot,
  cached after the first successful ``cmdeploy run``.
  Subsequent relay containers launch from this image
  so the deploy step is mostly no-ops (roughly 3× faster than a fresh deploy).
  Relay containers are limited to **500 MiB RAM** and the DNS container to **100 MiB**.


.. _lxc-tls:

TLS handling and underscore domains
------------------------------------

Container domains start with ``_`` (e.g. ``_test0.localchat``).
As described in :doc:`getting_started` ("Running a relay with self-signed certificates"),
underscore domains automatically use self-signed TLS
and ``smtp_tls_security_level = encrypt``.
This permits cross-relay federation between LXC containers
without any external certificate authority.
Delta Chat clients connecting to these relays
must be configured with
``certificateChecks = acceptInvalidCertificates``
(the test fixtures handle this automatically).
`PR #7926 on chatmail-core <https://github.com/chatmail/core/pull/7926>`_
is meant to make this special setting unnecessary for chatmail clients
that are connecting to underscore domains.


Known limitations
------------------

The LXC environment differs from a production
deployment in several ways:

**No ACME / Let's Encrypt**:
  Self-signed TLS only (see :ref:`lxc-tls`);
  ACME code paths are never exercised locally.

**No inbound connections from the internet**:
  Containers sit on a private Incus bridge and are not port-forwarded.
  Only the host and other containers on the same bridge can reach them.

**Local federation only**:
  Cross-relay mail delivery (e.g. test0 → test1) works between containers on the same host,
  but these relays are invisible to any external mail server.

**DNS is local only**:
  The ``.localchat`` pseudo-TLD is not resolvable from the wider internet
  (see :ref:`lxc-dns-setup`).

**IPv6 is ULA-only**:
  Containers receive IPv6 addresses from the ``fd42:...`` ULA range on the Incus bridge.
  These are not globally routable, but are sufficient for testing IPv6 service binding
  (Postfix, Dovecot, Nginx) and DNS AAAA records inside the local environment.
  test1 runs with ``disable_ipv6 = True`` to exercise the IPv4-only deployment path.
