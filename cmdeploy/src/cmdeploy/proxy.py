import importlib

from pyinfra import host
from pyinfra.operations import files, server, apt, systemd

def configure_ssh():
    files.replace(
        name="Configure sshd to use port 2222",
        path="/etc/ssh/sshd_config",
        text="Port 22\n",
        replace="Port 2222\n",
    )
    systemd.service(
        name="apply SSH config",
        service="ssh",
        reloaded=True,
    )
    apt.update()


def configure_proxy(ipv4_relay, ipv6_relay):
    files.put(
        name="Configure nftables",
        src=importlib.resources.files(__package__).joinpath("proxy_files/nftables.conf.j2"),
        dest="/etc/nftables.conf",
        ipv4_address=ipv4_relay,  # :todo what if only one of them is specified?
        ipv6_address=ipv6_relay,
    )

    server.sysctl(name="enable IPv4 forwarding", key="net.ipv4.ip_forward", value=1, persist=True)

    server.sysctl(
        name="enable IPv6 forwarding",
        key="net.ipv6.conf.all.forwarding",
        value=1,
        persist=True,
    )

    server.shell(
        name="apply forwarding configuration",
        commands=[
            "sysctl -p",
            "nft -f /etc/nftables.conf",
        ],
    )

    if host.data.get("floating_ips"):
        i = 0
        for floating_ip in host.data.get("floating_ips"):
            i += 1
            files.template(
                name="Add floating IPs",
                src="servers/proxy-nine/files/60-floating.ip.cfg.j2",
                dest=f"/etc/network/interfaces.d/{59 + i}-floating.ip.cfg",
                ip_address=floating_ip,
                i=i,
            )

        systemd.service(
            name="apply floating IPs",
            service="networking",
            restarted=True,
        )
