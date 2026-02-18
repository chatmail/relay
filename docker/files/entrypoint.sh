#!/bin/bash
set -eo pipefail

SETUP_CHATMAIL_SERVICE_PATH="${SETUP_CHATMAIL_SERVICE_PATH:-/lib/systemd/system/setup_chatmail.service}"

# Whitelist only the env vars needed by setup_chatmail_docker.sh.
# Forwarding all env vars (via printenv) would leak Docker internals,
# orchestrator secrets, and other unrelated variables into systemd.
env_vars="MAIL_DOMAIN CMDEPLOY_STAGES CHATMAIL_INI CHATMAIL_NOSYSCTL CHATMAIL_NOPORTCHECK CHATMAIL_NOACME PATH_TO_SSL PATH"
sed -i "s|<envs_list>|$env_vars|g" "$SETUP_CHATMAIL_SERVICE_PATH"

exec /lib/systemd/systemd "$@"
