
Community developments
======================

Active development takes place in the `chatmail/relay github repository <https://github.com/chatmail/relay>`_.

You can check out the `'chatmail' tag in the support.delta.chat forum <https://support.delta.chat/tag/chatmail>`_
and ask to get added to a non-public support chat for debugging issues.

We know of three work-in-progress alternative implementation efforts:

-  `Mox <https://github.com/mjl-/mox>`_: A Golang email server. `Work
   is in progress <https://github.com/mjl-/mox/issues/251>`_ to modify
   it to support all of the features and configuration settings required
   to operate as a chatmail relay.

-  `Madmail <https://github.com/themadorg/madmail>`_: an
   experimental fork of `Maddy Mail Server <https://maddy.email/>`_, modified
   for chatmail deployments.  It provides a single binary solution
   for running a chatmail relay.

-  `Chatmail Cookbook <https://github.com/feld/chatmail-cookbook>`_:
   A Chef Cookbook implementing a relay server. The project follows the
   official relay server software and configurations converted to a Chef
   Cookbook with only minor differences. The cookbook uses DNS-01 for
   certificate validation and additionally supports FreeBSD. It does not
   require a Chef server to use.
