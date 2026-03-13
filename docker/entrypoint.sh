#!/bin/bash
set -eo pipefail

CHATMAIL_INIT_SERVICE_PATH="${CHATMAIL_INIT_SERVICE_PATH:-/lib/systemd/system/chatmail-init.service}"

env_vars="MAIL_DOMAIN CMDEPLOY_STAGES CHATMAIL_INI TLS_EXTERNAL_CERT_AND_KEY PATH"
sed -i "s|<envs_list>|$env_vars|g" "$CHATMAIL_INIT_SERVICE_PATH"

exec /lib/systemd/systemd "$@"
