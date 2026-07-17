#!/bin/bash
#
# Show current IMAP and SMTP connections on a chatmail relay,
# to compare against the max_imap_connections and max_smtp_connections
# settings in chatmail.ini.  Run this on the relay itself.
set -e

# Count established TCP connections whose local port is one of the arguments.
established() {
    filter=$(printf 'sport = :%s or ' "$@")
    ss -Htn state established "( ${filter% or } )" | wc -l
}

# doveadm prints a header line and then one line per logged-in user,
# with that user's number of connections in the second column.
sessions=$(doveadm who | awk 'NR > 1 { n += $2 } END { print n + 0 }')

# Unless imap_compress is enabled, connections idle for
# imap_hibernate_timeout are handed over to the imap-hibernate
# process, so they cost no imap process while idle.
active=$(pgrep -x imap | wc -l)

printf 'imap        %6d  ports 143,993   (max_imap_connections)\n' "$(established 143 993)"
printf '            %6d  dovecot sessions, %d of them in an active imap process\n' "$sessions" "$active"
printf 'submission  %6d  ports 465,587   (max_smtp_connections per port)\n' "$(established 465 587)"
printf 'incoming    %6d  port 25         (from other relays, no chatmail.ini limit)\n' "$(established 25)"
