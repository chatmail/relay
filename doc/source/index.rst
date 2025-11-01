Chatmail relays for end-to-end encrypted e-mail
===============================================

.. toctree::
    :maxdepth: 4

    getting_started
    overview
    proxy
    migrate
    troubleshooting
    related
    architecture

Chatmail relay servers are interoperable Mail Transport Agents (MTAs)
designed for:

-  **Convenience:** Low friction instant onboarding

-  **Privacy:** No name, phone numbers, email required or collected

-  **End-to-End Encryption enforced**: only OpenPGP messages with
   metadata minimization allowed

-  **Instant:** Privacy-preserving Push Notifications for Apple, Google,
   and Huawei

-  **Speed:** Message delivery in half a second, with optional P2P
   realtime connections

-  **Transport Security:** Strict TLS and DKIM enforced

-  **Reliability:** No spam or IP reputation checks; rate-limits are
   suitable for realtime chats

-  **Efficiency:** Messages are only stored for transit and removed
   automatically

This repository contains everything needed to setup a ready-to-use
chatmail relay comprised of a minimal setup of the battle-tested
`Postfix SMTP <https://www.postfix.org>`_ and `Dovecot
IMAP <https://www.dovecot.org>`_ MTAs/MDAs.

The automated setup is designed and optimized for providing chatmail
addresses for immediate permission-free onboarding through chat apps and
bots. Chatmail addresses are automatically created at first login, after
which the initially specified password is required for sending and
receiving messages through them.

- `list of known apps and client projects <https://chatmail.at/clients.html>`_

- `this list of known public 3rd party chatmail relay servers <https://chatmail.at/relays>`_.



