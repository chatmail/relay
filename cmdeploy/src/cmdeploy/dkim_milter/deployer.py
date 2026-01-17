"""
Installs DKIM Milter.
"""

from pyinfra import facts, host
from pyinfra.facts.files import File, Sha256File
from pyinfra.operations import apt, files, server, systemd

from cmdeploy.basedeploy import Deployer, get_resource


class DkimMilterDeployer(Deployer):
    required_users = [("dkim-milter", None, ["dkim-milter"])]

    def __init__(self, mail_domain):
        self.mail_domain = mail_domain
        self.need_restart = False

    def install(self):
        """Builds and installs dkim-milter"""

        # openssl is required to generate the signing key
        apt.packages(
            name="Install openssl required by DKIM Milter",
            packages=["openssl"],
        )

        (url, sha256sum) = {
            "x86_64": (
                #"https://github.com/chatmail/dkim-milter/releases/download/0.1.0/dkim-milter-x86_64",
                # todo: replace with github release
                "https://kamiokan.de/bin/dkim-milter-x86_64",
                "c5e1c7688a04b2bead6586dd7491a1d29fb80b9edcca30ab5d638acdad024b77",
            ),
            "aarch64": (
                #"https://github.com/chatmail/dkim-milter/releases/download/0.1.0/dkim-milter-aarch64",
                # todo: replace with github release
                "https://kamiokan.de/bin/dkim-milter-aarch64",
                "9f1ce165c15da6ac10f7a7d90f5d64bf14a203f83587d9f7ee5936215a40e2b3",
            ),
        }[host.get_fact(facts.server.Arch)]

        existing_sha256sum = host.get_fact(Sha256File, "/usr/local/sbin/dkim-milter")
        if existing_sha256sum != sha256sum:
            server.shell(
                name="Download DKIM Milter",
                commands=[
                    f"(curl -L {url} >/usr/local/sbin/dkim-milter.new && (echo '{sha256sum} /usr/local/sbin/dkim-milter.new' | sha256sum -c) && mv /usr/local/sbin/dkim-milter.new /usr/local/sbin/dkim-milter)",
                    "chmod 755 /usr/local/sbin/dkim-milter",
                ],
            )
            self.need_restart = True

    def configure(self):
        """Configures dkim-milter"""

        domain = self.mail_domain
        # note - we are using "opendkim" for backward compatibility
        # for relays that were set up before we migrated from OpenDKIM
        # to DKIM Milter.
        selector = "opendkim"
        signing_key_name = selector
        # for backward compatibility with opendkim-genkey
        signing_key_filename = f"{signing_key_name}.private"
        config = {
            "domain": domain,
            "selector": selector,
            "signing_key_name": signing_key_name,
            "signing_key_filename": signing_key_filename,
        }

        self.need_restart |= files.directory(
            name="Create a directory for DKIM Milter config",
            path="/etc/dkim-milter",
            user="dkim-milter",
            group="dkim-milter",
            mode="750",
            present=True,
        ).changed

        self.need_restart |= files.directory(
            name="Create dkimkeys directory",
            path="/etc/dkimkeys",
            user="dkim-milter",
            group="dkim-milter",
            mode="750",
            present=True,
        ).changed

        self.need_restart |= files.template(
            src=get_resource("dkim_milter/dkim-milter.conf"),
            dest="/etc/dkim-milter/dkim-milter.conf",
            user="dkim-milter",
            group="dkim-milter",
            mode="644",
            config=config,
        ).changed

        self.need_restart |= files.template(
            src=get_resource("dkim_milter/signing-keys"),
            dest="/etc/dkim-milter/signing-keys",
            user="dkim-milter",
            group="dkim-milter",
            mode="644",
            config=config,
        ).changed

        self.need_restart |= files.template(
            src=get_resource("dkim_milter/signing-senders"),
            dest="/etc/dkim-milter/signing-senders",
            user="dkim-milter",
            group="dkim-milter",
            mode="644",
            config=config,
        ).changed

        self.need_restart |= files.directory(
            name="Create DKIM Milter unix socket directory",
            path="/var/spool/postfix/dkim-milter",
            user="dkim-milter",
            group="dkim-milter",
            mode="770",
        ).changed

        if not host.get_fact(File, f"/etc/dkimkeys/{signing_key_filename}"):
            server.shell(
                name=f"Generate DKIM Milter signing key '{signing_key_name}'",
                commands=[
                    f"openssl genpkey -algorithm RSA -out /etc/dkimkeys/{signing_key_filename}"
                ],
            )
            self.need_restart = True

        # enforce restrictive permissions for the signing key
        self.need_restart |= files.file(
            path=f"/etc/dkimkeys/{signing_key_filename}",
            present=True,
            user="dkim-milter",
            group="dkim-milter",
            mode="0400",
        ).changed

        self.need_restart |= files.put(
            name="Create dkim-milter service",
            src=get_resource("dkim_milter/dkim-milter.service"),
            dest="/etc/systemd/system/dkim-milter.service",
        ).changed

    def activate(self):
        """Start and enable DKIM Milter"""
        systemd.service(
            name="Start and enable DKIM Milter",
            service="dkim-milter.service",
            running=True,
            enabled=True,
            daemon_reload=self.need_restart,
            restarted=self.need_restart,
        )
        self.need_restart = False
