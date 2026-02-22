from pyinfra.operations import apt, files, server, systemd

from cmdeploy.basedeploy import Deployer, get_resource


class PostfixDeployer(Deployer):
    required_users = [("postfix", None, ["opendkim"])]
    daemon_reload = False

    def __init__(self, config, disable_mail):
        self.config = config
        self.disable_mail = disable_mail

    def install(self):
        apt.packages(
            name="Install Postfix",
            packages="postfix",
        )

    def configure(self):
        config = self.config
        need_restart = False

        main_config = files.template(
            src=get_resource("postfix/main.cf.j2"),
            dest="/etc/postfix/main.cf",
            user="root",
            group="root",
            mode="644",
            config=config,
            disable_ipv6=config.disable_ipv6,
        )
        need_restart |= main_config.changed

        master_config = files.template(
            src=get_resource("postfix/master.cf.j2"),
            dest="/etc/postfix/master.cf",
            user="root",
            group="root",
            mode="644",
            debug=False,
            config=config,
        )
        need_restart |= master_config.changed

        header_cleanup = files.put(
            src=get_resource("postfix/submission_header_cleanup"),
            dest="/etc/postfix/submission_header_cleanup",
            user="root",
            group="root",
            mode="644",
        )
        need_restart |= header_cleanup.changed

        lmtp_header_cleanup = files.put(
            src=get_resource("postfix/lmtp_header_cleanup"),
            dest="/etc/postfix/lmtp_header_cleanup",
            user="root",
            group="root",
            mode="644",
        )
        need_restart |= lmtp_header_cleanup.changed

        tls_policy_map = files.put(
            name="Upload SMTP TLS Policy that accepts self-signed certificates for IP-only hosts",
            src=get_resource("postfix/smtp_tls_policy_map"),
            dest="/etc/postfix/smtp_tls_policy_map",
            user="root",
            group="root",
            mode="644",
        )
        need_restart |= tls_policy_map.changed
        if tls_policy_map.changed:
            server.shell(
                commands=["postmap /etc/postfix/smtp_tls_policy_map"],
            )

        # Login map that 1:1 maps email address to login.
        login_map = files.put(
            src=get_resource("postfix/login_map"),
            dest="/etc/postfix/login_map",
            user="root",
            group="root",
            mode="644",
        )
        need_restart |= login_map.changed

        restart_conf = files.put(
            name="postfix: restart automatically on failure",
            src=get_resource("service/10_restart.conf"),
            dest="/etc/systemd/system/postfix@.service.d/10_restart.conf",
        )
        self.daemon_reload = restart_conf.changed

        # Validate postfix configuration before restart
        if need_restart:
            server.shell(
                name="Validate postfix configuration",
                # Extract stderr and quit with error if non-zero
                commands=[
                    """bash -c 'w=$(postconf 2>&1 >/dev/null); [[ -z "$w" ]] || { echo "$w"; false; }'"""
                ],
            )
        self.need_restart = need_restart

    def activate(self):
        restart = False if self.disable_mail else self.need_restart

        systemd.service(
            name=(
                "disable postfix for now"
                if self.disable_mail
                else "Start and enable Postfix"
            ),
            service="postfix.service",
            running=False if self.disable_mail else True,
            enabled=False if self.disable_mail else True,
            restarted=restart,
            daemon_reload=self.daemon_reload,
        )
        self.need_restart = False
