from chatmaild.config import Config
from pyinfra.operations import apt, files, systemd

from cmdeploy.basedeploy import (
    Deployer,
    get_resource,
)


class NginxDeployer(Deployer):
    def __init__(self, config):
        self.config = config

    def install(self):
        #
        # If we allow nginx to start up on install, it will grab port
        # 80, which then will block acmetool from listening on the port.
        # That in turn prevents getting certificates, which then causes
        # an error when we try to start nginx on the custom config
        # that leaves port 80 open but also requires certificates to
        # be present.  To avoid getting into that interlocking mess,
        # we use policy-rc.d to prevent nginx from starting up when it
        # is installed.
        #
        # This approach allows us to avoid performing any explicit
        # systemd operations during the install stage (as opposed to
        # allowing it to start and then forcing it to stop), which allows
        # the install stage to run in non-systemd environments like a
        # container image build.
        #
        # For documentation about policy-rc.d, see:
        # https://people.debian.org/~hmh/invokerc.d-policyrc.d-specification.txt
        #
        files.put(
            src=get_resource("policy-rc.d"),
            dest="/usr/sbin/policy-rc.d",
            user="root",
            group="root",
            mode="755",
        )

        apt.packages(
            name="Install nginx",
            packages=["nginx", "libnginx-mod-stream"],
        )

        files.file("/usr/sbin/policy-rc.d", present=False)

    def configure(self):
        self.need_restart = _configure_nginx(self.config)

    def activate(self):
        systemd.service(
            name="Start and enable nginx",
            service="nginx.service",
            running=True,
            enabled=True,
            restarted=self.need_restart,
        )
        self.need_restart = False


def _configure_nginx(config: Config, debug: bool = False) -> bool:
    """Configures nginx HTTP server."""
    need_restart = False

    main_config = files.template(
        src=get_resource("nginx/nginx.conf.j2"),
        dest="/etc/nginx/nginx.conf",
        user="root",
        group="root",
        mode="644",
        config={"domain_name": config.mail_domain},
        disable_ipv6=config.disable_ipv6,
    )
    need_restart |= main_config.changed

    autoconfig = files.template(
        src=get_resource("nginx/autoconfig.xml.j2"),
        dest="/var/www/html/.well-known/autoconfig/mail/config-v1.1.xml",
        user="root",
        group="root",
        mode="644",
        config={"domain_name": config.mail_domain},
    )
    need_restart |= autoconfig.changed

    mta_sts_config = files.template(
        src=get_resource("nginx/mta-sts.txt.j2"),
        dest="/var/www/html/.well-known/mta-sts.txt",
        user="root",
        group="root",
        mode="644",
        config={"domain_name": config.mail_domain},
    )
    need_restart |= mta_sts_config.changed

    # install CGI newemail script
    #
    cgi_dir = "/usr/lib/cgi-bin"
    files.directory(
        name=f"Ensure {cgi_dir} exists",
        path=cgi_dir,
        user="root",
        group="root",
    )

    files.put(
        name="Upload cgi newemail.py script",
        src=get_resource("newemail.py", pkg="chatmaild").open("rb"),
        dest=f"{cgi_dir}/newemail.py",
        user="root",
        group="root",
        mode="755",
    )

    return need_restart
