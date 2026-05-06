"""
Installs OpenDKIM
"""

from pyinfra import host
from pyinfra.facts.files import File
from pyinfra.operations import apt, files, server

from cmdeploy.basedeploy import Deployer


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

        self.put_template(
            "opendkim/opendkim.conf",
            "/etc/opendkim.conf",
            config={"domain_name": domain, "opendkim_selector": dkim_selector},
        )

        self.remove_file("/etc/opendkim/screen.lua")
        self.remove_file("/etc/opendkim/final.lua")

        self.ensure_directory(
            "/etc/opendkim",
            owner="opendkim",
            mode="750",
        )

        self.put_template(
            "opendkim/KeyTable",
            "/etc/dkimkeys/KeyTable",
            owner="opendkim",
            config={"domain_name": domain, "opendkim_selector": dkim_selector},
        )

        self.put_template(
            "opendkim/SigningTable",
            "/etc/dkimkeys/SigningTable",
            owner="opendkim",
            config={"domain_name": domain, "opendkim_selector": dkim_selector},
        )
        self.ensure_directory(
            "/var/spool/postfix/opendkim",
            owner="opendkim",
            mode="750",
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

        self.put_file(
            "opendkim/systemd.conf",
            "/etc/systemd/system/opendkim.service.d/10-prevent-memory-leak.conf",
        )

        files.file(
            name="chown opendkim: /etc/dkimkeys/opendkim.private",
            path="/etc/dkimkeys/opendkim.private",
            user="opendkim",
            group="opendkim",
        )

    def activate(self):
        self.ensure_service("opendkim.service")
