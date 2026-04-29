
from pyinfra.operations import apt, server, systemd

from ..basedeploy import Deployer


class AcmetoolDeployer(Deployer):
    def __init__(self, email, domains):
        self.domains = domains
        self.email = email
        self.need_restart_redirector = False
        self.need_restart_reconcile_service = False
        self.need_restart_reconcile_timer = False

    def install(self):
        apt.packages(
            name="Install acmetool",
            packages=["acmetool"],
        )

        self.remove_file("/etc/cron.d/acmetool")

        self.put_file(
            "acmetool/acmetool.hook", "/etc/acme/hooks/nginx", executable=True
        )
        self.remove_file("/usr/lib/acme/hooks/nginx")

    def configure(self):
        self.put_template(
            "acmetool/response-file.yaml.j2",
            "/var/lib/acme/conf/responses",
            email=self.email,
        )

        self.put_template(
            "acmetool/target.yaml.j2",
            "/var/lib/acme/conf/target",
        )

        server.shell(
            name=f"Remove old acmetool desired files for {self.domains[0]}",
            commands=[f"rm -f /var/lib/acme/desired/{self.domains[0]}-*"],
        )
        self.put_template(
            "acmetool/desired.yaml.j2",
            f"/var/lib/acme/desired/{self.domains[0]}",
            domains=self.domains,
        )

        service_file = self.ensure_systemd_unit("acmetool/acmetool-redirector.service")
        self.need_restart_redirector = service_file.changed

        reconcile_service_file = self.ensure_systemd_unit(
            "acmetool/acmetool-reconcile.service"
        )
        self.need_restart_reconcile_service = reconcile_service_file.changed

        reconcile_timer_file = self.ensure_systemd_unit(
            "acmetool/acmetool-reconcile.timer"
        )
        self.need_restart_reconcile_timer = reconcile_timer_file.changed

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


