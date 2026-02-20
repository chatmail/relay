from pyinfra import facts, host
from pyinfra.operations import files, systemd

from cmdeploy.basedeploy import Deployer, get_resource


class FiltermailDeployer(Deployer):
    services = ["filtermail", "filtermail-incoming"]
    bin_path = "/usr/local/bin/filtermail"
    config_path = "/usr/local/lib/chatmaild/chatmail.ini"

    def __init__(self):
        self.need_restart = False

    def install(self):
        arch = host.get_fact(facts.server.Arch)
        url = f"https://github.com/chatmail/filtermail/releases/download/v0.5.1/filtermail-{arch}"
        sha256sum = {
            "x86_64": "adce2ddb461c5fd744df699f3b0b3c33b6d52413c641f18695b93826e5e0d234",
            "aarch64": "b51cf4248c6c443308f21b1811da1cc919b98b719a2138f4b60940ea093a5422",
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
