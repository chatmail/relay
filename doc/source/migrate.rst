
Migrating to a new host
-----------------------

If you want to migrate chatmail relay from an old machine to a new
machine, you can use these steps. They were tested with a Linux laptop;
you might need to adjust some of the steps to your environment.

Let’s assume that your ``mail_domain`` is ``mail.example.org``, all
involved machines run Debian 12, your old site’s IP address is
``13.37.13.37``, and your new site’s IP address is ``13.12.23.42``.

Note, you should lower the TTLs of your DNS records to a value such as
300 (5 minutes) so the migration happens as smoothly as possible.

During the guide you might get a warning about changed SSH Host keys; in
this case, just run ``ssh-keygen -R "mail.example.org"`` as recommended.

1. First, disable mail services on the old site.

   ::

       cmdeploy run --disable-mail --ssh-host 13.37.13.37

   Now your users will notice the migration and will not be able to send
   or receive messages until the migration is completed.

2. Now we want to copy ``/home/vmail``, ``/var/lib/acme``,
   ``/etc/dkimkeys``, and ``/var/spool/postfix`` to
   the new site. Login to the old site while forwarding your SSH agent
   so you can copy directly from the old to the new site with your SSH
   key:

   ::

       ssh -A root@13.37.13.37
       tar c - /home/vmail/mail /var/lib/acme /etc/dkimkeys /var/spool/postfix | ssh root@13.12.23.42 "tar x -C /"

   This transfers all addresses, the TLS certificate,
   and DKIM keys (so DKIM DNS record remains valid).
   It also preserves the Postfix mail spool so any messages
   pending delivery will still be delivered.

3. Install chatmail on the new machine:

   ::

       cmdeploy run --disable-mail --ssh-host 13.12.23.42

   Postfix and Dovecot are disabled for now; we will enable them later.
   We first need to make the new site fully operational.

4. On the new site, run the following to ensure the ownership is correct
   in case UIDs/GIDs changed:

   ::

       chown root: -R /var/lib/acme
       chown opendkim: -R /etc/dkimkeys
       chown vmail: -R /home/vmail/mail

5. Now, update DNS entries.

   If other MTAs try to deliver messages to your chatmail domain they
   may fail intermittently, as DNS catches up with the new site settings
   but normally will retry delivering messages for at least a week, so
   messages will not be lost.

6. Finally, you can execute ``cmdeploy run --ssh-host 13.12.23.42`` to
   turn on chatmail on the new relay. Your users will be able to use the
   chatmail relay as soon as the DNS changes have propagated. Voilà!

