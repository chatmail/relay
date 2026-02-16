#!/bin/bash

set -eo pipefail
export CHATMAIL_INI="${CHATMAIL_INI:-/etc/chatmail/chatmail.ini}"

CMDEPLOY=/opt/cmdeploy/bin/cmdeploy

if [ -z "$MAIL_DOMAIN" ]; then
    echo "ERROR: Environment variable 'MAIL_DOMAIN' must be set!" >&2
    exit 1
fi

### MAIN

if [ ! -f /etc/dkimkeys/opendkim.private ]; then
    /usr/sbin/opendkim-genkey -D /etc/dkimkeys -d "$MAIL_DOMAIN" -s opendkim
fi
chown opendkim:opendkim /etc/dkimkeys/opendkim.private
chown opendkim:opendkim /etc/dkimkeys/opendkim.txt

# Create chatmail.ini (skips if file already exists, e.g. volume-mounted)
mkdir -p "$(dirname "$CHATMAIL_INI")"
if [ ! -f "$CHATMAIL_INI" ]; then
    $CMDEPLOY init --config "$CHATMAIL_INI" "$MAIL_DOMAIN"
fi

export CMDEPLOY_STAGES="${CMDEPLOY_STAGES:-configure,activate}"
$CMDEPLOY run --config "$CHATMAIL_INI" --ssh-host @local

# Journald: forward to console for docker logs (idempotent)
grep -q '^ForwardToConsole=yes' /etc/systemd/journald.conf \
    || echo "ForwardToConsole=yes" >> /etc/systemd/journald.conf
systemctl restart systemd-journald
