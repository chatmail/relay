from pyinfra import facts, host
from pyinfra.operations import apt

from cmdeploy.basedeploy import Deployer
from cmdeploy.filtermail.deployer import (
    MTAIL_PROGRAM_SHA256 as FILTERMAIL_MTAIL_SHA256,
    VERSION as FILTERMAIL_VERSION,
)


class MtailDeployer(Deployer):
    bin_path = "/usr/local/bin/mtail"
    progs_dir = "/etc/mtail"

    def __init__(self, mtail_address):
        self.mtail_address = mtail_address

    def install(self):
        # Uninstall mtail package to install a static binary.
        apt.packages(name="Uninstall mtail", packages=["mtail"], present=False)

        (url, sha256sum) = {
            "x86_64": (
                "https://github.com/google/mtail/releases/download/v3.0.8/mtail_3.0.8_linux_amd64.tar.gz",
                "d55cb601049c5e61eabab29998dbbcea95d480e5448544f9470337ba2eea882e",
            ),
            "aarch64": (
                "https://github.com/google/mtail/releases/download/v3.0.8/mtail_3.0.8_linux_arm64.tar.gz",
                "f748db8ad2a1e0b63684d4c8868cf6a373a20f7e6922e5ece601fff0ee00eb1a",
            ),
        }[host.get_fact(facts.server.Arch)]
        self.download_executable(
            url,
            self.bin_path,
            sha256sum,
            extract="gunzip | tar -xf - mtail -O",
        )

    def configure(self):
        # Using our own systemd unit instead of `/usr/lib/systemd/system/mtail.service`.
        # This allows to read from journalctl instead of log files.
        self.ensure_systemd_unit(
            "mtail/mtail.service.j2",
            address=self.mtail_address or "127.0.0.1",
            port=3903,
            bin_path=self.bin_path,
            progs_dir=self.progs_dir,
        )
        if self.mtail_address:
            self.put_file(
                "mtail/delivered_mail.mtail", f"{self.progs_dir}/delivered_mail.mtail"
            )
            self.download_executable(
                f"https://raw.githubusercontent.com/chatmail/filtermail/{FILTERMAIL_VERSION}/contrib/filtermail.mtail",
                f"{self.progs_dir}/filtermail.mtail",
                FILTERMAIL_MTAIL_SHA256,
                mode="644",
            )

    def activate(self):
        active = bool(self.mtail_address)
        self.ensure_service("mtail.service", running=active, enabled=active)
