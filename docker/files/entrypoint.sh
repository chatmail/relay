#!/bin/bash
set -eo pipefail

CHATMAIL_INIT_SERVICE_PATH="${CHATMAIL_INIT_SERVICE_PATH:-/lib/systemd/system/chatmail-init.service}"

# Whitelist only the env vars needed by chatmail-init.sh.
# Forwarding all env vars (via printenv) would leak Docker internals,
# orchestrator secrets, and other unrelated variables into systemd.
env_vars="MAIL_DOMAIN CMDEPLOY_STAGES CHATMAIL_INI TLS_EXTERNAL_CERT_AND_KEY PATH"
sed -i "s|<envs_list>|$env_vars|g" "$CHATMAIL_INIT_SERVICE_PATH"

exec /lib/systemd/systemd "$@"
