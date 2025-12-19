import importlib.resources

from pyinfra.operations import apt, files, server, systemd

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

        files.file(
            name="Remove old acmetool cronjob, it is replaced with systemd timer.",
            path="/etc/cron.d/acmetool",
            present=False,
        )

        files.put(
            name="Install acmetool hook.",
            src=importlib.resources.files(__package__)
            .joinpath("acmetool.hook")
            .open("rb"),
            dest="/etc/acme/hooks/nginx",
            user="root",
            group="root",
            mode="755",
        )
        files.file(
            name="Remove acmetool hook from the wrong location where it was previously installed.",
            path="/usr/lib/acme/hooks/nginx",
            present=False,
        )

    def configure(self):
        files.template(
            src=importlib.resources.files(__package__).joinpath(
                "response-file.yaml.j2"
            ),
            dest="/var/lib/acme/conf/responses",
            user="root",
            group="root",
            mode="644",
            email=self.email,
        )

        files.template(
            src=importlib.resources.files(__package__).joinpath("target.yaml.j2"),
            dest="/var/lib/acme/conf/target",
            user="root",
            group="root",
            mode="644",
        )

        server.shell(
            name=f"Remove old acmetool desired files for {self.domains[0]}",
            commands=[f"rm -f /var/lib/acme/desired/{self.domains[0]}-*"],
        )
        files.template(
            src=importlib.resources.files(__package__).joinpath("desired.yaml.j2"),
            dest=f"/var/lib/acme/desired/{self.domains[0]}", # 0 is mailhost TLD
            user="root",
            group="root",
            mode="644",
            domains=self.domains,
        )

        service_file = files.put(
            src=importlib.resources.files(__package__).joinpath(
                "acmetool-redirector.service"
            ),
            dest="/etc/systemd/system/acmetool-redirector.service",
            user="root",
            group="root",
            mode="644",
        )
        self.need_restart_redirector = service_file.changed

        reconcile_service_file = files.put(
            src=importlib.resources.files(__package__).joinpath(
                "acmetool-reconcile.service"
            ),
            dest="/etc/systemd/system/acmetool-reconcile.service",
            user="root",
            group="root",
            mode="644",
        )
        self.need_restart_reconcile_service = reconcile_service_file.changed

        reconcile_timer_file = files.put(
            src=importlib.resources.files(__package__).joinpath(
                "acmetool-reconcile.timer"
            ),
            dest="/etc/systemd/system/acmetool-reconcile.timer",
            user="root",
            group="root",
            mode="644",
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
