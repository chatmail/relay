#!/bin/bash
# returns 0 when chatmail-init succeeded and all expected services are running.

set -e

test -f /run/chatmail-init.done

# Core services
services="chatmail-metadata doveauth dovecot filtermail filtermail-incoming nginx postfix unbound"

# Optional services
for svc in iroh-relay turnserver; do
    systemctl is-enabled "$svc" 2>/dev/null && services="$services $svc"
done

exec systemctl is-active $services
