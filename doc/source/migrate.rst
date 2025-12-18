
Migrating to a new host
-----------------------

If you want to migrate chatmail relay from an old machine to a new
machine, you can use these steps. They were tested with a Linux laptop;
you might need to adjust some of the steps to your environment.

Let’s assume that your ``mail_domain`` is ``mail.example.org``, all
involved machines run Debian 12, your old site’s IP version 4 address is
``$OLD_IP4``, and your new site’s IP4 address is ``$NEW_IP4``.

First of all, you should lower the Time To Live (TTL) of your DNS records
to a value such as 300 (5 minutes).
Short TTL values allow to change DNS records during the migration more timely.

During the guide you might get a warning about changed SSH Host keys; in
this case, just run ``ssh-keygen -R "mail.example.org"`` as recommended.

1. First, to make the downtime during the migration shorter,
   let's transfer the current state of the mailboxes.
   Login to your old machine (while forwarding your ssh-agent with ``ssh -A``)
   so you can copy directly from the old to the new site with your SSH
   key:

   ::

       ssh -A root@$OLD_IP4
       tar c /home/vmail/mail | ssh root@$NEW_IP4 "tar x -C /"

   This saves us time during the downtime,
   at least the mailboxes are there already.
   They contain user passwords, encrypted push notification tokens,
   messages which might not have been fetched by all devices of the user yet,
   and dovecot indexes which track the state of the mailbox.

2. Then, from your local machine, install chatmail on the new machine, but don't activate it yet:

   ::

       CMDEPLOY_STAGES=install,configure cmdeploy run --ssh-host $NEW_IP4

   The services are disabled for now; we will enable them later.
   We first need to make the new site fully operational.

3. Now it's getting serious: disable the mail services on the old site.

   ::

       cmdeploy run --disable-mail --ssh-host $OLD_IP4

   Your users will start to notice the migration and will not be able to send
   or receive messages until the migration is completed.
   Other relays and mail servers will wait with delivering messages
   until your relay is reachable again.

4. Now we want to copy ``/home/vmail``, ``/var/lib/acme``,
   ``/etc/dkimkeys``, and ``/var/spool/postfix`` to
   the new site. Let's forward the SSH agent again to copy the files directly.
   This time, we copy ``/home/vmail/mail`` with rsync to only copy the recent changes:

   ::

       ssh -A root@$OLD_IP4
       tar c /var/lib/acme /etc/dkimkeys /var/spool/postfix | ssh root@$NEW_IP4 "tar x -C /"
       rsync -azH /home/vmail/mail root@$NEW_IP4:/home/vmail/

   This transfers all messages which have not been fetched yet, the TLS certificate,
   and DKIM keys (so DKIM DNS record remains valid).
   It also preserves the Postfix mail spool so any messages
   pending delivery will still be delivered.

5. Now login to the new site and run the following to ensure the ownership is correct
   in case UIDs/GIDs changed:

   ::

       ssh root@$NEW_IP4
       chown root: -R /var/lib/acme
       chown opendkim: -R /etc/dkimkeys
       chown vmail: -R /home/vmail/mail

6. Now, update the DNS entries.
   You only need to change the ``A`` and ``AAAA`` records, for example:

   ::

       mail.example.org.    IN A    $NEW_IP4
       mail.example.org.    IN AAAA $NEW_IP6

7. Finally, you can execute ``CMDEPLOY_STAGES=activate cmdeploy run --ssh-host $NEW_IP4`` to
   turn on chatmail on the new relay. Your users will be able to use the
   chatmail relay as soon as the DNS changes have propagated. Voilà!

