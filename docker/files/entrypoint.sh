#!/bin/bash
set -eo pipefail

unlink /etc/nginx/sites-enabled/default || true

SETUP_CHATMAIL_SERVICE_PATH="${SETUP_CHATMAIL_SERVICE_PATH:-/lib/systemd/system/setup_chatmail.service}"

env_vars=$(printenv | cut -d= -f1 | xargs)
sed -i "s|<envs_list>|$env_vars|g" $SETUP_CHATMAIL_SERVICE_PATH

exec /lib/systemd/systemd $@
