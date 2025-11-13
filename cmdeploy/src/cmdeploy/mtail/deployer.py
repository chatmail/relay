from pyinfra import facts, host
from pyinfra.operations import apt, files, server, systemd

from cmdeploy.basedeploy import (
    Deployer,
    get_resource,
)


class MtailDeployer(Deployer):
    def __init__(self, mtail_address):
        self.mtail_address = mtail_address

    def install(self):
        # Uninstall mtail package to install a static binary.
        apt.packages(name="Uninstall mtail", packages=["mtail"], present=False)

        (url, sha256sum) = {
            "x86_64": (
                "https://github.com/google/mtail/releases/download/v3.0.8/mtail_3.0.8_linux_amd64.tar.gz",
                "123c2ee5f48c3eff12ebccee38befd2233d715da736000ccde49e3d5607724e4",
            ),
            "aarch64": (
                "https://github.com/google/mtail/releases/download/v3.0.8/mtail_3.0.8_linux_arm64.tar.gz",
                "aa04811c0929b6754408676de520e050c45dddeb3401881888a092c9aea89cae",
            ),
        }[host.get_fact(facts.server.Arch)]

        server.shell(
            name="Download mtail",
            commands=[
                f"(echo '{sha256sum} /usr/local/bin/mtail' | sha256sum -c) || (curl -L {url} | gunzip | tar -x -f - mtail -O >/usr/local/bin/mtail.new && mv /usr/local/bin/mtail.new /usr/local/bin/mtail)",
                "chmod 755 /usr/local/bin/mtail",
            ],
        )

    def configure(self):
        # Using our own systemd unit instead of `/usr/lib/systemd/system/mtail.service`.
        # This allows to read from journalctl instead of log files.
        files.template(
            src=get_resource("mtail/mtail.service.j2"),
            dest="/etc/systemd/system/mtail.service",
            user="root",
            group="root",
            mode="644",
            address=self.mtail_address or "127.0.0.1",
            port=3903,
        )

        mtail_conf = files.put(
            name="Mtail configuration",
            src=get_resource("mtail/delivered_mail.mtail"),
            dest="/etc/mtail/delivered_mail.mtail",
            user="root",
            group="root",
            mode="644",
        )
        self.need_restart = mtail_conf.changed

    def activate(self):
        systemd.service(
            name="Start and enable mtail",
            service="mtail.service",
            running=bool(self.mtail_address),
            enabled=bool(self.mtail_address),
            restarted=self.need_restart,
        )
        self.need_restart = False
