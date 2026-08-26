from pyinfra import facts, host
from pyinfra.operations import apt, server

from cmdeploy.basedeploy import Deployer
from cmdeploy.pins import FILTERMAIL_ARTIFACTS, MTAIL_ARTIFACTS


class MtailDeployer(Deployer):
    bin_path = "/usr/local/bin/mtail"
    progs_dir = "/etc/mtail"

    def __init__(self, mtail_address):
        self.mtail_address = mtail_address

    def install(self):
        # Uninstall mtail package to install a static binary.
        apt.packages(name="Uninstall mtail", packages=["mtail"], present=False)

        (url, sha256sum) = MTAIL_ARTIFACTS[host.get_fact(facts.server.Arch)]
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
            url, sha256sum = FILTERMAIL_ARTIFACTS['mtail']
            self.download_executable(
                url,
                f"{self.progs_dir}/filtermail.mtail",
                sha256sum,
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
