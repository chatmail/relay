import os

from pyinfra import facts, host

from cmdeploy.basedeploy import Deployer
from cmdeploy.constants import BINARY_PATHS, CHATMAILD_PATHS


class FiltermailDeployer(Deployer):
    services = ["filtermail", "filtermail-incoming", "filtermail-transport"]
    bin_path = BINARY_PATHS["filtermail"]
    config_path = CHATMAILD_PATHS["config"]

    def install(self):
        local_bin = os.environ.get("CHATMAIL_FILTERMAIL_BINARY")
        if local_bin:
            self.put_executable(
                src=local_bin,
                dest=self.bin_path,
            )
            return

        arch = host.get_fact(facts.server.Arch)
        url = f"https://github.com/chatmail/filtermail/releases/download/v0.7.1/filtermail-{arch}"
        sha256sum = {
            "x86_64": "fc2d8141166f8561b9711fb68c5327fc9421f814c46dc69671a4605a95b175c0",
            "aarch64": "37e52c5ddb373ef29b5ead89658407c53f48d10ce055a2dbd9c606fa1ebd5f7f",
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
