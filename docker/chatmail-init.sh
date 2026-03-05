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

# Generate DKIM keys if not mounted
if [ ! -f /etc/dkimkeys/opendkim.private ]; then
    /usr/sbin/opendkim-genkey -D /etc/dkimkeys -d "$MAIL_DOMAIN" -s opendkim
fi
# Fix ownership for bind-mounted keys (host opendkim UID may differ from container)
chown -R opendkim:opendkim /etc/dkimkeys

# Create chatmail.ini, skip if mounted
mkdir -p "$(dirname "$CHATMAIL_INI")"
if [ ! -f "$CHATMAIL_INI" ]; then
    $CMDEPLOY init --config "$CHATMAIL_INI" "$MAIL_DOMAIN"
fi

# Auto-detect IPv6: if the host has no IPv6 connectivity, set disable_ipv6
# in the ini so dovecot/postfix/nginx bind to IPv4 only.
# Uses network_mode:host so /proc/net/if_inet6 reflects the host's stack.
if [ ! -e /proc/net/if_inet6 ]; then
    if grep -q '^disable_ipv6 = False' "$CHATMAIL_INI"; then
        sed -i 's/^disable_ipv6 = False/disable_ipv6 = True/' "$CHATMAIL_INI"
        echo "[INFO] IPv6 not available, set disable_ipv6 = True"
    fi
fi

# Inject external TLS paths from env var unless defined in chatmail.ini
if [ -n "${TLS_EXTERNAL_CERT_AND_KEY:-}" ]; then
    if ! grep -q '^tls_external_cert_and_key' "$CHATMAIL_INI"; then
        echo "tls_external_cert_and_key = $TLS_EXTERNAL_CERT_AND_KEY" >> "$CHATMAIL_INI"
    fi
fi

# Ensure mailboxes directory exists (chatmail-metadata needs it at startup,
# but Dovecot only creates it on first mail delivery)
mkdir -p "/home/vmail/mail/${MAIL_DOMAIN}"
chown vmail:vmail "/home/vmail/mail/${MAIL_DOMAIN}"

# --- Deploy fingerprint: skip cmdeploy run if nothing changed ---
# On restart with identical image+config, systemd already brings up all
# enabled services only configure+activate are needed here.
IMAGE_VERSION_FILE="/etc/chatmail-image-version"
FINGERPRINT_FILE="/etc/chatmail/.deploy-fingerprint"
image_ver="none"
[ -f "$IMAGE_VERSION_FILE" ] && image_ver=$(cat "$IMAGE_VERSION_FILE")
config_hash=$(sha256sum "$CHATMAIL_INI" | cut -c1-16)
current_fp="${image_ver}:${config_hash}"

# CMDEPLOY_STAGES non-empty in env = operator override -> always run.
# Otherwise, if fingerprint matches the last successful deploy, skip.
if [ -z "${CMDEPLOY_STAGES:-}" ] \
    && [ -f "$FINGERPRINT_FILE" ] \
    && [ "$(cat "$FINGERPRINT_FILE")" = "$current_fp" ]; then
    echo "[INFO] No changes detected ($current_fp), skipping deploy."
else
    export CMDEPLOY_STAGES="${CMDEPLOY_STAGES:-configure,activate}"

    # Skip DNS check when MAIL_DOMAIN is a bare IP address
    SKIP_DNS=""
    if [[ "$MAIL_DOMAIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || [[ "$MAIL_DOMAIN" =~ : ]]; then
        SKIP_DNS="--skip-dns-check"
    fi
    $CMDEPLOY run --config "$CHATMAIL_INI" --ssh-host @local $SKIP_DNS

    # Restore the build-time hash
    cp /etc/chatmail-image-version /etc/chatmail-version
    echo "$current_fp" > "$FINGERPRINT_FILE"
fi

# Signal success to Docker healthcheck
touch /run/chatmail-init.done

# Forward journald to console so `docker compose logs` works
grep -q '^ForwardToConsole=yes' /etc/systemd/journald.conf \
    || echo "ForwardToConsole=yes" >> /etc/systemd/journald.conf
systemctl restart systemd-journald
