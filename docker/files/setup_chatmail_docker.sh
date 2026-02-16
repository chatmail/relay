#!/bin/bash

set -eo pipefail
export CHATMAIL_INI="${CHATMAIL_INI:-/etc/chatmail/chatmail.ini}"

CMDEPLOY=/opt/cmdeploy/bin/cmdeploy

if [ -z "$MAIL_DOMAIN" ]; then
    echo "ERROR: Environment variable 'MAIL_DOMAIN' must be set!" >&2
    exit 1
fi

### MAIN

if [ ! -f /etc/dkimkeys/opendkim.private ]; then
    /usr/sbin/opendkim-genkey -D /etc/dkimkeys -d "$MAIL_DOMAIN" -s opendkim
fi
chown opendkim:opendkim /etc/dkimkeys/opendkim.private
chown opendkim:opendkim /etc/dkimkeys/opendkim.txt

# Create chatmail.ini (skips if file already exists, e.g. volume-mounted)
mkdir -p "$(dirname "$CHATMAIL_INI")"
if [ ! -f "$CHATMAIL_INI" ]; then
    $CMDEPLOY init --config "$CHATMAIL_INI" "$MAIL_DOMAIN"
fi

# Auto-detect image upgrades: if the image version changed since last run,
# include the install stage so new packages/binaries are picked up.
IMAGE_VERSION_FILE="/etc/chatmail-image-version"
RUNNING_VERSION_FILE="/home/.chatmail-running-version"
CMDEPLOY_STAGES="${CMDEPLOY_STAGES:-configure,activate}"
if [ -f "$IMAGE_VERSION_FILE" ]; then
    image_ver=$(cat "$IMAGE_VERSION_FILE")
    running_ver=""
    if [ -f "$RUNNING_VERSION_FILE" ]; then
        running_ver=$(cat "$RUNNING_VERSION_FILE")
    fi
    if [ "$image_ver" != "$running_ver" ]; then
        echo "[INFO] Image version changed ($running_ver -> $image_ver), adding install stage."
        case "$CMDEPLOY_STAGES" in
            *install*) ;;  # already includes install
            *) CMDEPLOY_STAGES="install,$CMDEPLOY_STAGES" ;;
        esac
    fi
fi
export CMDEPLOY_STAGES
$CMDEPLOY run --config "$CHATMAIL_INI" --ssh-host @local

# Record successful version after deploy
if [ -f "$IMAGE_VERSION_FILE" ]; then
    cp "$IMAGE_VERSION_FILE" "$RUNNING_VERSION_FILE"
fi

# Journald: forward to console for docker logs (idempotent)
grep -q '^ForwardToConsole=yes' /etc/systemd/journald.conf \
    || echo "ForwardToConsole=yes" >> /etc/systemd/journald.conf
systemctl restart systemd-journald
