from pyinfra.operations import apt, server, systemd

from cmdeploy.basedeploy import Deployer


class PostfixDeployer(Deployer):
    required_users = [("postfix", None, ["opendkim"])]

    def __init__(self, config, disable_mail):
        super().__init__()
        self.config = config
        self.disable_mail = disable_mail

    def install(self):
        apt.packages(
            name="Install Postfix",
            packages="postfix",
        )

    def configure(self):
        config = self.config

        self.put_template(
            "postfix/main.cf.j2",
            "/etc/postfix/main.cf",
            config=config,
            disable_ipv6=config.disable_ipv6,
        )

        self.put_template(
            "postfix/master.cf.j2",
            "/etc/postfix/master.cf",
            debug=False,
            config=config,
        )

        self.put_file(
            "postfix/submission_header_cleanup",
            "/etc/postfix/submission_header_cleanup",
        )
        self.put_file("postfix/lmtp_header_cleanup", "/etc/postfix/lmtp_header_cleanup")

        res = self.put_file(
            "postfix/smtp_tls_policy_map", "/etc/postfix/smtp_tls_policy_map"
        )
        tls_policy_changed = res.changed
        if tls_policy_changed:
            server.shell(
                commands=["postmap /etc/postfix/smtp_tls_policy_map"],
            )

        # Login map that 1:1 maps email address to login.
        self.put_file("postfix/login_map", "/etc/postfix/login_map")

        self.put_file(
            "service/10_restart_on_failure.conf",
            "/etc/systemd/system/postfix@.service.d/10_restart.conf",
        )

        # Validate postfix configuration before restart
        if self.need_restart:
            server.shell(
                name="Validate postfix configuration",
                # Extract stderr and quit with error if non-zero
                commands=[
                    """bash -c 'w=$(postconf 2>&1 >/dev/null); [[ -z "$w" ]] || { echo "$w"; false; }'"""
                ],
            )

    def activate(self):
        restart = False if self.disable_mail else self.need_restart

        systemd.service(
            name="disable postfix for now"
            if self.disable_mail
            else "Start and enable Postfix",
            service="postfix.service",
            running=False if self.disable_mail else True,
            enabled=False if self.disable_mail else True,
            restarted=restart,
            daemon_reload=self.daemon_reload,
        )
        self.need_restart = False
