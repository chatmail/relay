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
        url = f"https://github.com/chatmail/filtermail/releases/download/v0.6.6/filtermail-{arch}"
        sha256sum = {
            "x86_64": "05c7e7ac244606c2eeb275f2d282ffdbc2403e0169f1cdd3110ffcebdb994a92",
            "aarch64": "8cf8bbda4d907beca547b365cc7e6753532a74b1712492d0d2f3d2d8a553fb3d",
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
