#!/bin/bash

set -eo pipefail
export INI_FILE="${INI_FILE:-chatmail.ini}"
export ENABLE_CERTS_MONITORING="${ENABLE_CERTS_MONITORING:-true}"
export CERTS_MONITORING_TIMEOUT="${CERTS_MONITORING_TIMEOUT:-60}"
export PATH_TO_SSL_CONTAINER="${PATH_TO_SSL_CONTAINER:-/var/lib/acme/live/${MAIL_DOMAIN}}"

if [ -z "$MAIL_DOMAIN" ]; then
    echo "ERROR: Environment variable 'MAIL_DOMAIN' must be set!" >&2
    exit 1
fi

debug_commands() {
    echo "Executing debug commands"
    # git config --global --add safe.directory /opt/chatmail
    # ./scripts/initenv.sh
}

calculate_hash() {
    find "$PATH_TO_SSL_CONTAINER" -type f -exec sha1sum {} \; | sort | sha1sum | awk '{print $1}'
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
            echo "[INFO] Certificate's folder hash was changed, restarting nginx, dovecot and postfix services."
            systemctl restart nginx.service
            systemctl reload dovecot.service
            systemctl reload postfix.service
            previous_hash=$current_hash
        fi
        sleep $CERTS_MONITORING_TIMEOUT
    done
}

### MAIN

if [ "$DEBUG_COMMANDS_ENABLED" == "true" ]; then
    debug_commands
fi

if [ "$FORCE_REINIT_INI_FILE" == "true" ]; then 
    INI_CMD_ARGS=--force
fi

/usr/sbin/opendkim-genkey -D /etc/dkimkeys -d $MAIL_DOMAIN -s opendkim
chown opendkim:opendkim /etc/dkimkeys/opendkim.private
chown opendkim:opendkim /etc/dkimkeys/opendkim.txt

# TODO: Move to debug_commands after git clone is moved to dockerfile. 
git config --global --add safe.directory /opt/chatmail
./scripts/initenv.sh

./scripts/cmdeploy init --config "${INI_FILE}" $INI_CMD_ARGS $MAIL_DOMAIN
bash /update_ini.sh

./scripts/cmdeploy run --ssh-host localhost --skip-dns-check

echo "ForwardToConsole=yes" >> /etc/systemd/journald.conf
systemctl restart systemd-journald

monitor_certificates &
