Removing a chatmail relay
==========================

This section explains how to remove a chatmail relay from a deployment server.

.. warning::

   ``cmdeploy remove`` is destructive.
   It removes chatmail services, configuration, mailbox data,
   DKIM keys, ACME or self-signed TLS state, static web pages,
   relay users and groups, and packages installed for the relay.
   If you are moving a relay to another server,
   follow :doc:`migrate` instead.


Preliminary notes and assumptions
---------------------------------

- You have the local relay repository checkout and Python virtualenv,
  initialized with ``scripts/initenv.sh``.

- You have the ``chatmail.ini`` file for the relay you want to remove.

- You have SSH root access to the deployment server.

- Your chatmail domain is ``chat.example.org``.

- DNS records at your DNS provider are not removed by ``cmdeploy remove``.
  Remove or update them separately after the relay is gone.
  If your DNS contains a CAA record with a Let's Encrypt ``accounturi``,
  remove it or change it before deploying this relay again,
  because ``cmdeploy remove`` deletes the local ACME account state.


Preview removal
---------------

First do a dry run from your local build machine:

::

   scripts/cmdeploy remove --dry-run --ssh-host chat.example.org

This shows the pyinfra operations that would run
without modifying the deployment server.


Remove the relay
----------------

To remove the relay, run:

::

   scripts/cmdeploy remove --ssh-host chat.example.org

The command asks you to type the chatmail domain
before it removes data from the server.
For scripted use, pass ``--yes`` to skip this confirmation:

::

   scripts/cmdeploy remove --ssh-host chat.example.org --yes


Keeping installed packages
--------------------------

If you want to remove chatmail state and configuration
but keep Debian packages such as Postfix, Dovecot, Nginx and Unbound installed,
use ``--keep-packages``:

::

   scripts/cmdeploy remove --ssh-host chat.example.org --keep-packages

This still removes chatmail-managed service units, configuration files,
mailboxes, web files, local chatmail binaries, and relay users,
while leaving package-owned default configuration files in place.


What remains
------------

``cmdeploy remove`` only acts on the deployment server.
It does not remove:

- DNS records at your DNS provider.
  In particular, a CAA record with a Let's Encrypt ``accounturi``
  still points to the removed ACME account.

- The local ``chatmail.ini`` file on your build machine.

- Externally managed TLS certificate and key files configured with
  ``tls_external_cert_and_key``.

If you want to use the server for something else,
check your firewall, monitoring, DNS, and hosting-provider settings after removal.
