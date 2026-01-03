# Testing with LXC

To test the relay setup in a local LXC container (tested on Arch Linux host):

### 1. Host Preparation
Install the necessary packages:
```bash
sudo pacman -S lxc arch-install-scripts dnsmasq
```

### 2. Network Configuration
If your host system has IPv6 disabled, you must disable it for LXC as well to avoid service failures:
Edit `/etc/default/lxc-net` and ensure these lines exist:
```bash
USE_LXC_BRIDGE="true"
LXC_IPV6_ENABLE="false"
LXC_IPV6_NAT="false"
```
*Note: If port 53 is occupied (e.g., by dnscrypt-proxy), you may need to configure your DNS service to listen only on `127.0.0.1` so LXC's dnsmasq can bind to the bridge.*

Restart the network:
```bash
sudo systemctl enable --now lxc-net.service
```

### 3. Create and Prepare Container
Create a Debian 12 (bookworm) container:
```bash
sudo lxc-create -n test -t download -- -d debian -r bookworm -a amd64
sudo lxc-start -n test
```

Sync your local repository to the container:
```bash
sudo rsync -av --exclude=.git ./ /var/lib/lxc/test/rootfs/relay-ir/
```

### 4. Run Deployment
Attach to the container and run the deployment locally:
```bash
sudo lxc-attach -n test -- bash -c "cd /relay-ir && ./scripts/initenv.sh && ./scripts/cmdeploy run --ssh-host @local --skip-dns-check"
```
