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
        url = f"https://github.com/chatmail/filtermail/releases/download/v0.6.4/filtermail-{arch}"
        sha256sum = {
            "x86_64": "5295115952c72e4c4ec3c85546e094b4155a4c702c82bd71fcdcb744dc73adf6",
            "aarch64": "6892244f17b8f26ccb465766e96028e7222b3c8adefca9fc6bfe9ff332ca8dff",
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
