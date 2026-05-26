import os

from pyinfra import facts, host

from cmdeploy.basedeploy import Deployer


class FiltermailDeployer(Deployer):
    services = ["filtermail", "filtermail-incoming", "filtermail-transport"]
    bin_path = "/usr/local/bin/filtermail"
    config_path = "/usr/local/lib/chatmaild/chatmail.ini"

    def install(self):
        local_bin = os.environ.get("CHATMAIL_FILTERMAIL_BINARY")
        if local_bin:
            self.put_executable(
                src=local_bin,
                dest=self.bin_path,
            )
            return

        arch = host.get_fact(facts.server.Arch)
        url = f"https://github.com/chatmail/filtermail/releases/download/v0.7.0/filtermail-{arch}"
        sha256sum = {
            "x86_64": "451f295a85b3b12dbb0f89e18ec319f742ee46dec218f20f7923bfb017a248bd",
            "aarch64": "6833061b2a2028264fdeb32f0a6123e1ff73de57dace125364016300b748452e",
        }[arch]
        self.download_executable(url, self.bin_path, sha256sum)

    def configure(self):
        for service in self.services:
            self.ensure_systemd_unit(
                f"filtermail/{service}.service.j2",
                bin_path=self.bin_path,
                config_path=self.config_path,
            )

    def activate(self):
        for service in self.services:
            self.ensure_service(f"{service}.service")
