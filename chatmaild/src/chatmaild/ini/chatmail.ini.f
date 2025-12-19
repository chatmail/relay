[params]

# mail domain (MUST be set to fully qualified chat mail domain)
mail_domain = {mail_domain}

#
# If you only do private test deploys, you don't need to modify any settings below
#

#
# Restrictions on user addresses
#

# how many mails a user can send out per minute
max_user_send_per_minute = 60

# maximum mailbox size of a chatmail address
max_mailbox_size = 100M

# maximum message size for an e-mail in bytes
max_message_size = 31457280

# days after which mails are unconditionally deleted
delete_mails_after = 20

# days after which large messages (>200k) are unconditionally deleted
delete_large_after = 7

# days after which users without a successful login are deleted (database and mails)
delete_inactive_users_after = 90

# minimum length a username must have
username_min_length = 9

# maximum length a username can have
username_max_length = 9

# minimum length a password must have
password_min_length = 9

# list of chatmail addresses which can send outbound un-encrypted mail
passthrough_senders =

# list of e-mail recipients for which to accept outbound un-encrypted mails
# (space-separated, item may start with "@" to whitelist whole recipient domains)
passthrough_recipients =

# path to www directory - documented here: https://chatmail.at/doc/relay/getting_started.html#custom-web-pages
#www_folder = www

#
# Deployment Details
#

# SMTP outgoing filtermail and reinjection 
filtermail_smtp_port = 10080
postfix_reinject_port = 10025

# SMTP incoming filtermail and reinjection 
filtermail_smtp_port_incoming = 10081
postfix_reinject_port_incoming = 10026

# if set to "True" IPv6 is disabled
disable_ipv6 = False

# Your email adress, which will be used in acmetool to manage Let's Encrypt SSL certificates
acme_email = 

# Defaults to https://iroh.{{mail_domain}} and running `iroh-relay` on the chatmail
# service.
# If you set it to anything else, the service will be disabled
# and users will be directed to use the given iroh relay URL.
# Set it to empty string if you want users to use their default iroh relay.
# iroh_relay =

# Address on which `mtail` listens,
# e.g. 127.0.0.1 or some private network
# address like 192.168.10.1.
# You can point Prometheus
# or some other OpenMetrics-compatible
# collector to
# http://{{mtail_address}}:3903/metrics
# and display collected metrics with Grafana.
#
# WARNING: do not expose this service
# to the public IP address.
#
# `mtail is not running if the setting is not set.

# mtail_address = 127.0.0.1

#
# Debugging options 
#

# set to True if you want to track imap protocol execution
# in per-maildir ".in/.out" files. 
# Note that you need to manually cleanup these files
# so use this option with caution on production servers. 
imap_rawlog = false 

# set to true if you want to enable the IMAP COMPRESS Extension,
# which allows IMAP connections to be efficiently compressed.
# WARNING: Enabling this makes it impossible to hibernate IMAP
# processes which will result in much higher memory/RAM usage.
imap_compress = false


#
# Privacy Policy
#

# postal address of privacy contact
privacy_postal =

# email address of privacy contact
privacy_mail =

# postal address of the privacy data officer
privacy_pdo =

# postal address of the privacy supervisor
privacy_supervisor =
