Configuring reverse DNS
=======================

Some email servers reject the emails
if they don't pass `FCrDNS`_ check, also known as `iprev`_ check.

.. _FCrDNS: https://en.wikipedia.org/wiki/Forward-confirmed_reverse_DNS
.. _iprev: https://datatracker.ietf.org/doc/html/rfc8601#section-3

Passing the check requires that the IP address that email is sent from
should have a ``PTR`` record pointing to the domain name of the server,
and domain name record should have an ``A/AAAA`` record
pointing to the IP address.

Modern email relies on DKIM and SPF for authentication,
while iprev check exists for
`historical reasons <https://datatracker.ietf.org/doc/html/draft-ietf-dnsop-reverse-mapping-considerations-06#section-2.1>`_.
Chatmail relays don't resolve ``PTR`` records,
so you can ignore this section if configuring ``PTR`` records
is difficult and federation with legacy email servers that don't accept
valid DKIM signature for authentication is not important.

Multi-homed setups
------------------

If you have a server with multiple IP addresses,
also known as multi-homed setup,
and don't publish all IP addresses in DNS,
you need to make sure you are using
the published address when making outgoing connections.

For example, your server may have a static IP
address, and a so-called Floating IP or Virtual IP
that can be moved between servers in case of
migration or for failover.
By using Floating IP you can avoid downtime
and keep the IP address reputation
for destinatinons that rely on IP reputation and IP blocklists.
In this case you will only publish
the Floating IP to DNS and only use the static IP
to SSH into the server.

If you have such setup, make sure that
you not only set ``PTR`` records for the Floating IP,
but make outgoing connections using the Floating IP.
Otherwise reverse DNS check succeed,
but forward check making sure your domain name points
to the IP address will fail.
Such setup is indistinguishable from someone
setting IP address ``PTR`` with the domain they don't own
and as a result don't succeed.

On Linux you can configure source IP address with ``ip route`` command,
for example:
::

  ip route change default via <default-gateway> dev eth0 src <source-address>

Make sure to persist the change after verifying it is working.
You can check what your outgoing IP address is
with ``curl icanhazip.com``.
Check both the IPv4 and IPv6 addresses.
For IPv4 address use ``curl ipv4.icanhazip.com`` or ``curl -4 icanhazip.com``
and similarly for IPv6 if you have it.
