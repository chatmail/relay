#!/bin/bash

set -eo pipefail
export CHATMAIL_INI="${CHATMAIL_INI:-/etc/chatmail/chatmail.ini}"
export ENABLE_CERTS_MONITORING="${ENABLE_CERTS_MONITORING:-true}"
export CERTS_MONITORING_TIMEOUT="${CERTS_MONITORING_TIMEOUT:-60}"
export PATH_TO_SSL="${PATH_TO_SSL:-/var/lib/acme/live/${MAIL_DOMAIN}}"

CMDEPLOY=/opt/cmdeploy/bin/cmdeploy

if [ -z "$MAIL_DOMAIN" ]; then
    echo "ERROR: Environment variable 'MAIL_DOMAIN' must be set!" >&2
    exit 1
fi

calculate_hash() {
    find "$PATH_TO_SSL" -type f -exec sha1sum {} \; | sort | sha1sum | awk '{print $1}'
}

monitor_certificates() {
    if [ "$ENABLE_CERTS_MONITORING" != "true" ]; then
        echo "Certs monitoring disabled."
        exit 0
    fi

    current_hash=$(calculate_hash)
    previous_hash=$current_hash

    while true; do
        current_hash=$(calculate_hash)
        if [[ "$current_hash" != "$previous_hash" ]]; then
        # TODO: add an option to restart at a specific time interval 
            echo "[INFO] Certificate's folder hash was changed, reloading nginx, dovecot and postfix services."
            systemctl reload nginx.service
            systemctl reload dovecot.service
            systemctl reload postfix.service
            previous_hash=$current_hash
        fi
        sleep $CERTS_MONITORING_TIMEOUT
    done
}

### MAIN

if [ ! -f /etc/dkimkeys/opendkim.private ]; then
    /usr/sbin/opendkim-genkey -D /etc/dkimkeys -d $MAIL_DOMAIN -s opendkim
fi
chown opendkim:opendkim /etc/dkimkeys/opendkim.private
chown opendkim:opendkim /etc/dkimkeys/opendkim.txt

# Create chatmail.ini (skips if file already exists, e.g. volume-mounted)
mkdir -p "$(dirname "$CHATMAIL_INI")"
$CMDEPLOY init --config "$CHATMAIL_INI" $MAIL_DOMAIN || true

export CMDEPLOY_STAGES="${CMDEPLOY_STAGES:-configure,activate}"
$CMDEPLOY run --ssh-host @docker

echo "ForwardToConsole=yes" >> /etc/systemd/journald.conf
systemctl restart systemd-journald

monitor_certificates &
