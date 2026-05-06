.. _iponly:

Hosting without DNS records
===========================

.. note::

   This option is experimental and might change without notice.

In case you don't have a domain,
for example in a local network,
you can run a chatmail relay with only an IPv4 address as well.

To deploy a relay without a domain,
run ``cmdeploy init`` with only the IPv4 address
during the :ref:`installation steps <setup>`,
for example ``cmdeploy init 13.12.23.42``.

Drawbacks
---------

- your transport encryption will only use self-signed TLS certificates,
  which are vulnerable against MITM attacks.
  the chatmail core's end-to-end encryption should suffice in most scenarios though.

- your messages will not be DKIM-signed;
  experimentally, most chatmail relays accept non-DKIM-signed messages from IPv4-only relays,
  but some relays might not accept messages from yours.

