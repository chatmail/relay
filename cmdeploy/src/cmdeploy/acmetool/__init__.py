from pyinfra.operations import apt, server

from ..basedeploy import Deployer


class AcmetoolDeployer(Deployer):
    def __init__(self, email, domains):
        self.domains = domains
        self.email = email

    def install(self):
        apt.packages(
            name="Install acmetool",
            packages=["acmetool"],
        )

        self.remove_file("/etc/cron.d/acmetool")

        self.put_executable("acmetool/acmetool.hook", "/etc/acme/hooks/nginx")
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

        self.ensure_systemd_unit("acmetool/acmetool-redirector.service")
        self.ensure_systemd_unit("acmetool/acmetool-reconcile.service")
        self.ensure_systemd_unit("acmetool/acmetool-reconcile.timer")

    def activate(self):
        self.ensure_service("acmetool-redirector.service")
        self.ensure_service("acmetool-reconcile.service", running=False, enabled=False)
        self.ensure_service("acmetool-reconcile.timer")

        server.shell(
            name=f"Reconcile certificates for: {', '.join(self.domains)}",
            commands=["acmetool --batch --xlog.severity=debug reconcile"],
        )
