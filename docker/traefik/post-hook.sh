#!/bin/sh
# Post-hook for traefik-certs-dumper: create symlinks from Traefik's
# cert dump format to the paths chatmail expects (fullchain, privkey).
CERTS_DIR="${CERTS_DIR:-/certs}"

for dir in "$CERTS_DIR"/*/; do
    [ -d "$dir" ] || continue
    cd "$dir"
    [ -f "certificate.crt" ] && ln -sf certificate.crt fullchain
    [ -f "privatekey.key" ] && ln -sf privatekey.key privkey
    cd - > /dev/null
done
