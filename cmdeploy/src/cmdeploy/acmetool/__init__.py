import importlib.resources
import io

from pyinfra.operations import apt, files, server, systemd

from ..basedeploy import Deployer

_acmetool_res = importlib.resources.files("cmdeploy.tls.acmetool")
_external_res = importlib.resources.files("cmdeploy.tls.external")


class AcmetoolDeployer(Deployer):
    def __init__(self, email, domains):
        self.domains = domains
        self.email = email
        self.need_restart_redirector = False
        self.need_restart_reconcile_service = False
        self.need_restart_reconcile_timer = False

    def remove_legacy_files(self):
        files.file(
            name="Remove old acmetool cronjob",
            path="/etc/cron.d/acmetool",
            present=False,
        )
        files.file(
            name="Remove acmetool hook from wrong location",
            path="/usr/lib/acme/hooks/nginx",
            present=False,
        )

    def install(self):
        self.remove_legacy_files()
        apt.packages(
            name="Install acmetool",
            packages=["acmetool"],
        )
        self.put_file(
            name="Deploy acmetool hook",
            dest="/etc/acme/hooks/nginx",
            src=_acmetool_res.joinpath("acmetool.hook").open("rb"),
            executable=True,
        )

    def configure(self):
        server.shell(
            name=f"Remove old acmetool desired files for {self.domains[0]}",
            commands=[f"rm -f /var/lib/acme/desired/{self.domains[0]}-*"],
        )

        setup_targets = [
            (
                "Setup acmetool responses",
                "response-file.yaml.j2",
                "/var/lib/acme/conf/responses",
            ),
            (
                "Setup acmetool target",
                "target.yaml.j2",
                "/var/lib/acme/conf/target",
            ),
            (
                f"Setup acmetool desired domains for {self.domains[0]}",
                "desired.yaml.j2",
                f"/var/lib/acme/desired/{self.domains[0]}",
            ),
        ]

        for name, src, dest in setup_targets:
            self.put_template(
                name=name,
                src=_acmetool_res.joinpath(src),
                dest=dest,
                email=self.email,
                domains=self.domains,
            )

        for basename, _, _ in self.services:
            res = self.put_file(
                name=f"Setup {basename}",
                src=_acmetool_res.joinpath(basename),
                dest=f"/etc/systemd/system/{basename}",
            )
            self.service_changed[basename] = res.changed

    def activate(self):
        systemd.service(
            name="Setup acmetool-redirector service",
            service="acmetool-redirector.service",
            running=True,
            enabled=True,
            restarted=self.need_restart_redirector,
        )
        self.need_restart_redirector = False

        systemd.service(
            name="Setup acmetool-reconcile service",
            service="acmetool-reconcile.service",
            running=False,
            enabled=False,
            daemon_reload=self.need_restart_reconcile_service,
        )
        self.need_restart_reconcile_service = False

        systemd.service(
            name="Setup acmetool-reconcile timer",
            service="acmetool-reconcile.timer",
            running=True,
            enabled=True,
            daemon_reload=self.need_restart_reconcile_timer,
        )
        self.need_restart_reconcile_timer = False

        server.shell(
            name=f"Reconcile certificates for: {', '.join(self.domains)}",
            commands=["acmetool --batch --xlog.severity=debug reconcile"],
        )


