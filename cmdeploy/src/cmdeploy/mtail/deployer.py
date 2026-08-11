from pyinfra import facts, host
from pyinfra.operations import apt, server

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
                "https://github.com/jaqx0r/mtail/releases/download/v3.4.9/mtail_3.4.9_linux_amd64.tar.gz",
                "55f64a87f71955bb871c724b4aadf19fe9d854e6327196919c7fe44943427eab",
            ),
            "aarch64": (
                "https://github.com/jaqx0r/mtail/releases/download/v3.4.9/mtail_3.4.9_linux_arm64.tar.gz",
                "e0a2b66b372ca257d7daeb7ba10f9233a2192a1f9057618fccc6be5c854a2a3c",
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
            if self.need_restart:
                # Check if all installed mtail rules compile or fail early
                # --one_shot to exit, --port 0 to not clash with running mtail.
                server.shell(
                    name="Validate mtail programs",
                    commands=[
                        f"timeout 30 {self.bin_path} --compile_only --one_shot"
                        f" --progs {self.progs_dir} --logs /dev/null"
                        " --address 127.0.0.1 --port 0"
                    ],
                )

    def activate(self):
        active = bool(self.mtail_address)
        self.ensure_service("mtail.service", running=active, enabled=active)
