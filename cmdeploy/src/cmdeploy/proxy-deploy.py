import os

import pyinfra
from pyinfra import host

from proxy import configure_ssh, configure_proxy


def main():
    ipv4_relay = os.getenv("IPV4_RELAY")
    ipv6_relay = os.getenv("IPV6_RELAY")

    configure_ssh()
    if host.data.get("ssh_port") not in (None, 22):
        configure_proxy(ipv4_relay, ipv6_relay)


if pyinfra.is_cli:
    main()
