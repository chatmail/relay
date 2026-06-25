from chatmaild.config import Config
from pyinfra.operations import apt

from cmdeploy.basedeploy import (
    Deployer,
    get_resource,
)
from cmdeploy.constants import CONFIG_FILES, WEB_PATHS


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
        self.put_executable(src="policy-rc.d", dest=CONFIG_FILES["policy_rc_d"])

        apt.packages(
            name="Install nginx",
            packages=["nginx", "libnginx-mod-stream"],
        )

        self.remove_file(CONFIG_FILES["policy_rc_d"])

    def configure(self):
        _configure_nginx(self, self.config)

    def activate(self):
        self.ensure_service("nginx.service")


def _configure_nginx(deployer, config: Config, debug: bool = False):
    """Configures nginx HTTP server."""

    deployer.put_template(
        "nginx/nginx.conf.j2",
        CONFIG_FILES["nginx_conf"],
        config=config,
        disable_ipv6=config.disable_ipv6,
    )

    deployer.put_template(
        "nginx/autoconfig.xml.j2",
        WEB_PATHS["autoconfig"],
        config=config,
    )

    deployer.put_template(
        "nginx/mta-sts.txt.j2",
        WEB_PATHS["mta_sts"],
        config=config,
    )

    # install CGI newemail script
    #
    cgi_dir = WEB_PATHS["newemail_cgi"].rsplit("/", 1)[0]
    deployer.ensure_directory(cgi_dir)

    deployer.put_executable(
        src=get_resource("newemail.py", pkg="chatmaild").open("rb"),
        dest=WEB_PATHS["newemail_cgi"],
    )
