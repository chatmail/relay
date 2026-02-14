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
        url = f"https://github.com/chatmail/filtermail/releases/download/v0.3.0/filtermail-{arch}"
        sha256sum = {
            "x86_64": "f14a31323ae2dad3b59d3fdafcde507521da2f951a9478cd1f2fe2b4463df71d",
            "aarch64": "933770d75046c4fd7084ce8d43f905f8748333426ad839154f0fc654755ef09f",
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
