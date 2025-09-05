#!/bin/bash
set -eo pipefail

unlink /etc/nginx/sites-enabled/default || true

if [ "${USE_FOREIGN_CERT_MANAGER,,}" = true ]; then
    if [ ! -f "$PATH_TO_SSL/fullchain" ]; then
        echo "Error: file '$PATH_TO_SSL/fullchain' does not exist. Exiting..." > /dev/stderr
        sleep 2
        exit 1
    fi
    if [ ! -f "$PATH_TO_SSL/privkey" ]; then
        echo "Error: file '$PATH_TO_SSL/privkey' does not exist. Exiting..." > /dev/stderr
        sleep 2
        exit 1
    fi
fi

SETUP_CHATMAIL_SERVICE_PATH="${SETUP_CHATMAIL_SERVICE_PATH:-/lib/systemd/system/setup_chatmail.service}"

# In systemd, you must EXPLICITLY specify which environment variables will be used by the process.
# If they are not specified, the systemd unit will be started without variables.
# This is a temporary solution until we completely move away from using systemd in the container.
env_vars=$(printenv | cut -d= -f1 | xargs)
sed -i "s|<envs_list>|$env_vars|g" $SETUP_CHATMAIL_SERVICE_PATH

exec /lib/systemd/systemd $@
