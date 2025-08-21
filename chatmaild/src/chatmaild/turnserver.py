#!/usr/bin/env python3
import base64
import hashlib
import hmac
import subprocess
import sys
import tempfile
import time


def coturn_credentials() -> str:
    secret = "north"

    ttl = 5 * 24 * 3600  # Time to live
    timestamp = int(time.time()) + ttl
    username = str(timestamp)
    dig = hmac.new(secret.encode(), username.encode(), hashlib.sha1).digest()
    password = base64.b64encode(dig).decode()

    return f"{username}:{password}"


def ips():
    output = subprocess.run(
        ["ip", "-o", "addr", "show", "scope", "global"], check=True, capture_output=True
    ).stdout.decode()
    for line in output.splitlines():
        ip_and_mask = line.split()[3]
        yield ip_and_mask.split("/")[0]


def generate_interfaces():
    """Generate `interfaces` section for TURN server config."""
    for ip in ips():
        # Wrap IPv6 in brackets.
        if ":" in ip:
            ip_config = f"[{ip}]"
        else:
            ip_config = ip

        for transport in "udp", "tcp":
            yield {
                "transport": transport,
                "bind": f"{ip_config}:3478",
                "external": f"{ip_config}:3478",
            }


def generate_config(hostname):
    """Generate TOML config for the TURN server."""
    config = f"""[turn]
realm = "{hostname}"

[log]
level = "info"

[auth]
static_auth_secret = "north"

[auth.static_credentials]
ohV8aec1 = "zo3theiY"
"""

    for interface in generate_interfaces():
        config += f"""
[[turn.interfaces]]
transport = "{interface["transport"]}"
bind = "{interface["bind"]}"
external = "{interface["external"]}"
"""

    return config


def main():
    hostname = sys.argv[1]
    config = generate_config(hostname)

    with tempfile.NamedTemporaryFile() as fp:
        fp.write(config.encode())
        fp.flush()
        subprocess.run(["/usr/local/bin/turn-server", "--config", fp.name], check=False)


if __name__ == "__main__":
    main()
