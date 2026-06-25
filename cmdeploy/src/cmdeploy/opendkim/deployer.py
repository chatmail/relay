"""
Installs OpenDKIM
"""

from pyinfra import host
from pyinfra.facts.files import File
from pyinfra.operations import apt, files, server

from cmdeploy.basedeploy import Deployer
from cmdeploy.constants import CONFIG_DIRS, CONFIG_FILES, STATE_DIRS


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
            CONFIG_FILES["opendkim_conf"],
            config={"domain_name": domain, "opendkim_selector": dkim_selector},
        )

        self.remove_file(f"{CONFIG_DIRS['opendkim']}/screen.lua")
        self.remove_file(f"{CONFIG_DIRS['opendkim']}/final.lua")

        self.ensure_directory(
            CONFIG_DIRS["opendkim"],
            owner="opendkim",
            mode="750",
        )

        self.put_template(
            "opendkim/KeyTable",
            f"{CONFIG_DIRS['dkimkeys']}/KeyTable",
            owner="opendkim",
            config={"domain_name": domain, "opendkim_selector": dkim_selector},
        )

        self.put_template(
            "opendkim/SigningTable",
            f"{CONFIG_DIRS['dkimkeys']}/SigningTable",
            owner="opendkim",
            config={"domain_name": domain, "opendkim_selector": dkim_selector},
        )
        self.ensure_directory(
            f"{STATE_DIRS['var_spool_postfix']}/opendkim",
            owner="opendkim",
            mode="750",
        )

        dkim_private_key = f"{CONFIG_DIRS['dkimkeys']}/{dkim_selector}.private"
        if not host.get_fact(File, dkim_private_key):
            server.shell(
                name="Generate OpenDKIM domain keys",
                commands=[
                    f"/usr/sbin/opendkim-genkey -D {CONFIG_DIRS['dkimkeys']} -d {domain} -s {dkim_selector}"
                ],
                _use_su_login=True,
                _su_user="opendkim",
            )

        self.put_file(
            "opendkim/systemd.conf",
            CONFIG_FILES["systemd_opendkim_restart"],
        )

        files.file(
            name=f"chown opendkim: {dkim_private_key}",
            path=dkim_private_key,
            user="opendkim",
            group="opendkim",
        )

    def activate(self):
        self.ensure_service("opendkim.service")
