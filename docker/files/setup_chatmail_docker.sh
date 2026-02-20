#!/bin/bash

set -euo pipefail
export CHATMAIL_INI="${CHATMAIL_INI:-/etc/chatmail/chatmail.ini}"
export CHATMAIL_NOSYSCTL=True
export CHATMAIL_NOPORTCHECK=True

CMDEPLOY=/opt/cmdeploy/bin/cmdeploy

if [ -z "$MAIL_DOMAIN" ]; then
    echo "ERROR: Environment variable 'MAIL_DOMAIN' must be set!" >&2
    exit 1
fi

### MAIN

if [ ! -f /etc/dkimkeys/opendkim.private ]; then
    /usr/sbin/opendkim-genkey -D /etc/dkimkeys -d "$MAIL_DOMAIN" -s opendkim
fi
# Fix ownership for bind-mounted keys (host opendkim UID may differ from container)
chown -R opendkim:opendkim /etc/dkimkeys

# Journald: forward to console for docker logs
grep -q '^ForwardToConsole=yes' /etc/systemd/journald.conf \
    || echo "ForwardToConsole=yes" >> /etc/systemd/journald.conf
systemctl restart systemd-journald

# Create chatmail.ini (skips if file already exists, e.g. volume-mounted)
mkdir -p "$(dirname "$CHATMAIL_INI")"
if [ ! -f "$CHATMAIL_INI" ]; then
    $CMDEPLOY init --config "$CHATMAIL_INI" "$MAIL_DOMAIN"
fi

# Inject external TLS paths from env var (unless user mounted their own ini)
if [ -n "${TLS_EXTERNAL_CERT_AND_KEY:-}" ]; then
    if ! grep -q '^tls_external_cert_and_key' "$CHATMAIL_INI"; then
        echo "tls_external_cert_and_key = $TLS_EXTERNAL_CERT_AND_KEY" >> "$CHATMAIL_INI"
    fi
fi

# --- Deploy fingerprint: skip cmdeploy run if nothing changed ---
# On restart with identical image+config, systemd already brings up all
# enabled services — the full cmdeploy run is redundant (~30s saved).
# The install stage runs at image build time (Dockerfile), so only
# configure+activate are needed here.
IMAGE_VERSION_FILE="/etc/chatmail-image-version"
FINGERPRINT_FILE="/etc/chatmail/.deploy-fingerprint"
image_ver="none"
[ -f "$IMAGE_VERSION_FILE" ] && image_ver=$(cat "$IMAGE_VERSION_FILE")
config_hash=$(sha256sum "$CHATMAIL_INI" | cut -c1-16)
current_fp="${image_ver}:${config_hash}"

# CMDEPLOY_STAGES non-empty in env = operator override → always run.
# Otherwise, if fingerprint matches the last successful deploy, skip.
if [ -z "${CMDEPLOY_STAGES:-}" ] \
    && [ -f "$FINGERPRINT_FILE" ] \
    && [ "$(cat "$FINGERPRINT_FILE")" = "$current_fp" ]; then
    echo "[INFO] No changes detected ($current_fp), skipping deploy."
else
    export CMDEPLOY_STAGES="${CMDEPLOY_STAGES:-configure,activate}"
    $CMDEPLOY run --config "$CHATMAIL_INI" --ssh-host @local
    echo "$current_fp" > "$FINGERPRINT_FILE"
fi
