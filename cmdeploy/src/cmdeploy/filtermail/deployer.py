from pyinfra import facts, host
from pyinfra.operations import files, systemd

from cmdeploy.basedeploy import Deployer


class FiltermailDeployer(Deployer):
    services = ["filtermail", "filtermail-incoming"]
    bin_path = "/usr/local/bin/filtermail"
    config_path = "/usr/local/lib/chatmaild/chatmail.ini"

    def install(self):
        arch = host.get_fact(facts.server.Arch)
        url = f"https://github.com/chatmail/filtermail/releases/download/v0.5.2/filtermail-{arch}"
        sha256sum = {
            "x86_64": "ce24ca0075aa445510291d775fb3aea8f4411818c7b885ae51a0fe18c5f789ce",
            "aarch64": "c5d783eefa5332db3d97a0e6a23917d72849e3eb45da3d16ce908a9b4e5a797d",
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
            self.put_template(
                f"filtermail/{service}.service.j2",
                f"/etc/systemd/system/{service}.service",
                bin_path=self.bin_path,
                config_path=self.config_path,
            )

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
