"""
Installs OpenDKIM
"""

from pyinfra import host
from pyinfra.facts.files import File
from pyinfra.operations import apt, files, server, systemd

from cmdeploy.basedeploy import Deployer, get_resource


class OpendkimDeployer(Deployer):
    required_users = [("opendkim", None, ["opendkim"])]

    def __init__(self, mail_domain):
        self.mail_domain = mail_domain

    def install(self):
        apt.packages(
            name="apt install opendkim opendkim-tools",
            packages=["opendkim", "opendkim-tools"],
        )

    def configure(self):
        domain = self.mail_domain
        dkim_selector = "opendkim"
        """Configures OpenDKIM"""
        need_restart = False

        main_config = files.template(
            src=get_resource("opendkim/opendkim.conf"),
            dest="/etc/opendkim.conf",
            user="root",
            group="root",
            mode="644",
            config={"domain_name": domain, "opendkim_selector": dkim_selector},
        )
        need_restart |= main_config.changed

        screen_script = files.put(
            src=get_resource("opendkim/screen.lua"),
            dest="/etc/opendkim/screen.lua",
            user="root",
            group="root",
            mode="644",
        )
        need_restart |= screen_script.changed

        final_script = files.put(
            src=get_resource("opendkim/final.lua"),
            dest="/etc/opendkim/final.lua",
            user="root",
            group="root",
            mode="644",
        )
        need_restart |= final_script.changed

        files.directory(
            name="Add opendkim directory to /etc",
            path="/etc/opendkim",
            user="opendkim",
            group="opendkim",
            mode="750",
            present=True,
        )

        keytable = files.template(
            src=get_resource("opendkim/KeyTable"),
            dest="/etc/dkimkeys/KeyTable",
            user="opendkim",
            group="opendkim",
            mode="644",
            config={"domain_name": domain, "opendkim_selector": dkim_selector},
        )
        need_restart |= keytable.changed

        signing_table = files.template(
            src=get_resource("opendkim/SigningTable"),
            dest="/etc/dkimkeys/SigningTable",
            user="opendkim",
            group="opendkim",
            mode="644",
            config={"domain_name": domain, "opendkim_selector": dkim_selector},
        )
        need_restart |= signing_table.changed
        files.directory(
            name="Add opendkim socket directory to /var/spool/postfix",
            path="/var/spool/postfix/opendkim",
            user="opendkim",
            group="opendkim",
            mode="750",
            present=True,
        )

        if not host.get_fact(File, f"/etc/dkimkeys/{dkim_selector}.private"):
            server.shell(
                name="Generate OpenDKIM domain keys",
                commands=[
                    f"/usr/sbin/opendkim-genkey -D /etc/dkimkeys -d {domain} -s {dkim_selector}"
                ],
                _use_su_login=True,
                _su_user="opendkim",
            )

        service_file = files.put(
            name="Configure opendkim to restart once a day",
            src=get_resource("opendkim/systemd.conf"),
            dest="/etc/systemd/system/opendkim.service.d/10-prevent-memory-leak.conf",
        )
        need_restart |= service_file.changed

        self.need_restart = need_restart

    def activate(self):
        systemd.service(
            name="Start and enable OpenDKIM",
            service="opendkim.service",
            running=True,
            enabled=True,
            daemon_reload=self.need_restart,
            restarted=self.need_restart,
        )
        self.need_restart = False
