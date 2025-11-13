

Frequently asked questions
===========================

What is the difference between chatmail relays and classic email servers?
--------------------------------------------------------------------------

A chatmail relay is a minimal Mail Transport Agent (MTA) setup that
goes beyond what classic email servers offer:

-  **Zero State:** no private data or metadata collected, messages are auto-deleted, low disk usage

-  **Instant/Realtime:** sub-second message delivery, realtime P2P
   streaming, privacy-preserving Push Notifications for Apple, Google, and `Ubuntu Touch <https://docs.ubports.com/en/latest/appdev/guides/pushnotifications.html>`_;

-  **Security Enforcement**: only strict TLS, DKIM and OpenPGP with minimized metadata accepted

-  **Reliable Federation and Decentralization:** No spam or IP reputation checks, federating
   depends on established IETF standards and protocols.


How about interoperability with classic email servers?
-------------------------------------------------------

Generally, chatmail relays interoperate well with classic email servers.
However, some chatmail relays may be blocked by Big-Tech email
providers that use intransparent and proprietary techniques for scanning
and looking at cleartext email messages between users, or because they
use questionable IP-reputation systems that break interoperability.

**Chatmail relays instead use and require strong cryptography, allowing
anyone to participate, without having to submit to Big-Tech
restrictions.**

.. _selfhosted:

How are chatmail relays run? Can I run one myself?
--------------------------------------------------

Chatmail relays are designed to be very cheap to run, and are generally
self-funded by respective operators. All chatmail relays are
automatically deployed and updated using `the chatmail relay
repository <https://github.com/chatmail/relay>`__. Chatmail relays are
composed of proven standard email server components, Postfix and
Dovecot, and are configured to run unattended without much maintenance
effort. Chatmail relays happily run on low-end hardware like a Raspberry
Pi.


How trustable are chatmail relays?
----------------------------------

Chatmail relays enforce end-to-end encryption,
and chatmail clients like `Delta Chat <https://delta.chat>`_
enforce end-to-end encryption on their own.

The end-to-end encryption protection includes attached media, user
display names, avatars and group names. What is visible to operators is:
message date, sender and receiver addresses.
Please see the `Delta Chat FAQ on encryption and security <https://delta.chat/en/help#e2ee>`_ for further info.
