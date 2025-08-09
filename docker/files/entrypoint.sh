#!/bin/bash
set -eo pipefail

if [ "${USE_FOREIGN_CERT_MANAGER,,}" == "true" ]; then
    if [ ! -f "$PATH_TO_SSL_CONTAINER/fullchain" ]; then
        echo "Error: file '$PATH_TO_SSL_CONTAINER/fullchain' does not exist. Exiting..." > /dev/stderr
        exit 1
    fi
    if [ ! -f "$PATH_TO_SSL_CONTAINER/privkey" ]; then
        echo "Error: file '$PATH_TO_SSL_CONTAINER/privkey' does not exist. Exiting..." > /dev/stderr
        exit 1
    fi
fi

SETUP_CHATMAIL_SERVICE_PATH="${SETUP_CHATMAIL_SERVICE_PATH:-/lib/systemd/system/setup_chatmail.service}"

env_vars=$(printenv | cut -d= -f1 | xargs)
sed -i "s|<envs_list>|$env_vars|g" $SETUP_CHATMAIL_SERVICE_PATH

exec /lib/systemd/systemd $@
