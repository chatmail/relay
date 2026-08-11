import os

from pyinfra import facts, host

from cmdeploy.basedeploy import Deployer

VERSION = "v0.7.4" # also gets used by mtail deployer
SHA256SUMS = {
    "x86_64": "484cb8dff083134aefba9fce4a6b7ef4784a0f0e28e5108ecf8bb9e58a44fd2c",
    "aarch64": "66aa0ca2ca9add7a12d92883d76f8786384092adfde24a3d3a1d0b1f30d23a9e",
}
MTAIL_PROGRAM_SHA256 = "948f688bb89ad47e6eb0fc8fa107e201a689f5adc264ff926be487a2a8562b51"


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
        url = f"https://github.com/chatmail/filtermail/releases/download/{VERSION}/filtermail-{arch}"
        self.download_executable(url, self.bin_path, SHA256SUMS[arch])

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
