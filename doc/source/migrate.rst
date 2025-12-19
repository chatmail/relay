
Migrating to a new machine
===========================

This migration tutorial provides a step-wise approach
to safely migrate a chatmail relay from one remote machine to another.

Preliminary notes and assumptions
---------------------------------

- If the migration is a planned move,
  it's recommended to lower the Time To Live (TTL) of your DNS records to a value such as 300 (5 minutes),
  at best much earlier than the actual planned migration.
  This speeds up propagation of DNS changes in the Internet after the migration is complete.

- The migration steps were tested with a Linux laptop; you might need to adjust some of the steps to your local environment.

- Your ``mail_domain`` is ``mail.example.org``.

- All remote machines run Debian 12.

- The old site’s IP version 4 address is ``$OLD_IP4``.

- The new site’s IP addresses are ``$NEW_IP4`` and ``$NEW_IPV6``.


The six steps to migrate
------------------------

Note that during some of the following steps you might get a warning about changed SSH Host keys;
in this case, just run ``ssh-keygen -R "mail.example.org"`` as recommended.


1. **Initially transfer mailboxes from old to new site.**

   Login to old site, forwarding your ssh-agent with ``ssh -A``
   to allow using ssh to directly copy files from old to new site.
   ::

       ssh -A root@$OLD_IP4
       tar c /home/vmail/mail | ssh root@$NEW_IP4 "tar x -C /"


2. **Pre-configure the new site but keep it inactive until step 6**
   ::

       CMDEPLOY_STAGES=install,configure cmdeploy run --ssh-host $NEW_IP4


3. **It's getting serious: disable mail services on the old site.**
   Users will not be able to send or receive messages until all steps are completed.
   Other relays and mail servers will retry delivering messages from time to time,
   so nothing is lost for users.

   ::

       cmdeploy run --disable-mail --ssh-host $OLD_IP4


4. **Final synchronization of TLS/DKIM secrets, mail queues and mailboxes.**
   Again we use ssh-agent forwarding (``-A``) to allow transfering all important data directly
   from the old to the new site.
   ::

       ssh -A root@$OLD_IP4
       tar c /var/lib/acme /etc/dkimkeys /var/spool/postfix | ssh root@$NEW_IP4 "tar x -C /"
       rsync -azH /home/vmail/mail root@$NEW_IP4:/home/vmail/

   Login to the new site and ensure file ownerships are correctly set:

   ::

       ssh root@$NEW_IP4
       chown root: -R /var/lib/acme
       chown opendkim: -R /etc/dkimkeys
       chown vmail: -R /home/vmail/mail


5. **Update the DNS entries to point to the new site.**
   You only need to change the ``A`` and ``AAAA`` records, for example:

   ::

       mail.example.org.    IN A    $NEW_IP4
       mail.example.org.    IN AAAA $NEW_IP6


6. **Activate chatmail relay on new site.**

   ::

        CMDEPLOY_STAGES=activate cmdeploy run --ssh-host $NEW_IP4

   Voilà!
   Users will be able to use the relay as soon as the DNS changes have propagated.
   If you have lowered the Time-to-Live for DNS records in step 1,
   better use a higher value again (between 14400 and 86400 seconds) once you are sure everything works.

