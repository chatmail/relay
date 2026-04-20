import os

from pyinfra import facts, host
from pyinfra.operations import files, systemd

from cmdeploy.basedeploy import Deployer, get_resource


class FiltermailDeployer(Deployer):
    services = ["filtermail", "filtermail-incoming", "filtermail-transport"]
    bin_path = "/usr/local/bin/filtermail"
    config_path = "/usr/local/lib/chatmaild/chatmail.ini"

    def __init__(self):
        self.need_restart = False

    def install(self):
        local_bin = os.environ.get("CHATMAIL_FILTERMAIL_BINARY")
        if local_bin:
            self.need_restart |= files.put(
                name="Upload locally built filtermail",
                src=local_bin,
                dest=self.bin_path,
                mode="755",
            ).changed
            return

        arch = host.get_fact(facts.server.Arch)
        url = f"https://github.com/chatmail/filtermail/releases/download/v0.6.3/filtermail-{arch}"
        sha256sum = {
            "x86_64": "87fac5715840d1bfb39742407d7911cce067a265dc47bda108acae58ce5f6086",
            "aarch64": "496004c5d0da1e64a559a23400d0fcebbe0b92a0fd31b30e6851f4987c3c7984",
        }[arch]
        self.need_restart |= files.download(
            name="Download filtermail",
            src=url,
            sha256sum=sha256sum,
            dest=self.bin_path,
            mode="755",
        ).changed

    def configure(self):
        for service in self.services:
            self.need_restart |= files.template(
                src=get_resource(f"filtermail/{service}.service.j2"),
                dest=f"/etc/systemd/system/{service}.service",
                user="root",
                group="root",
                mode="644",
                bin_path=self.bin_path,
                config_path=self.config_path,
            ).changed

    def activate(self):
        for service in self.services:
            systemd.service(
                name=f"Start and enable {service}",
                service=f"{service}.service",
                running=True,
                enabled=True,
                restarted=self.need_restart,
                daemon_reload=True,
            )
        self.need_restart = False
