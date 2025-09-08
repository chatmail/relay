import importlib.resources

from pyinfra.operations import apt, files, server, systemd

from ..deployer import Deployer


class AcmetoolDeployer(Deployer):
    def __init__(self, *, email, domains, **kwargs):
        super().__init__(**kwargs)
        self.domains = domains
        self.email = email
        self.need_restart = False

    @staticmethod
    def install_impl():
        apt.packages(
            name="Install acmetool",
            packages=["acmetool"],
        )

    def configure_impl(self):
        files.put(
            src=importlib.resources.files(__package__).joinpath("acmetool.cron").open("rb"),
            dest="/etc/cron.d/acmetool",
            user="root",
            group="root",
            mode="644",
        )

        files.put(
            src=importlib.resources.files(__package__).joinpath("acmetool.hook").open("rb"),
            dest="/usr/lib/acme/hooks/nginx",
            user="root",
            group="root",
            mode="744",
        )

        files.template(
            src=importlib.resources.files(__package__).joinpath("response-file.yaml.j2"),
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

        service_file = files.put(
            src=importlib.resources.files(__package__).joinpath(
                "acmetool-redirector.service"
            ),
            dest="/etc/systemd/system/acmetool-redirector.service",
            user="root",
            group="root",
            mode="644",
        )
        self.need_restart = service_file.changed

    def activate_impl(self):
        systemd.service(
            name="Setup acmetool-redirector service",
            service="acmetool-redirector.service",
            running=True,
            enabled=True,
            restarted=self.need_restart,
        )
        self.need_restart = False

        server.shell(
            name=f"Request certificate for: {', '.join(self.domains)}",
            commands=[f"acmetool want --xlog.severity=debug {' '.join(self.domains)}"],
        )
