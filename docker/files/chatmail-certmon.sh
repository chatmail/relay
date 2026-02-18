#!/bin/bash
# Check if TLS certificates have changed and reload services if so.
# Called by chatmail-certmon.timer (systemd timer, default every 60s).
set -eo pipefail

PATH_TO_SSL="${PATH_TO_SSL:-/var/lib/acme/live/${MAIL_DOMAIN}}"
HASH_FILE="/run/chatmail-certmon.hash"

if [ ! -d "$PATH_TO_SSL" ]; then
    exit 0
fi

current_hash=$(find "$PATH_TO_SSL" -type f -exec sha1sum {} \; | sort | sha1sum | awk '{print $1}')
previous_hash=""
if [ -f "$HASH_FILE" ]; then
    previous_hash=$(cat "$HASH_FILE")
fi

if [ -n "$current_hash" ] && [ "$current_hash" != "$previous_hash" ]; then
    echo "[INFO] Certificate hash changed, reloading nginx, dovecot and postfix."
    echo "$current_hash" > "$HASH_FILE"
    # On first run (no previous hash), don't reload — services may not be up yet
    if [ -n "$previous_hash" ]; then
        systemctl reload nginx.service
        systemctl reload dovecot.service
        systemctl reload postfix.service
    fi
fi
