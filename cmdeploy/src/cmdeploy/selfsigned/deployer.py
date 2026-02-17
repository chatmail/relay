from pyinfra.operations import apt, files, server

from cmdeploy.basedeploy import Deployer


class SelfSignedTlsDeployer(Deployer):
    """Generates a self-signed TLS certificate for all chatmail endpoints."""

    def __init__(self, mail_domain):
        self.mail_domain = mail_domain
        self.cert_path = "/etc/ssl/certs/mailserver.pem"
        self.key_path = "/etc/ssl/private/mailserver.key"

    def install(self):
        apt.packages(
            name="Install openssl",
            packages=["openssl"],
        )

    def configure(self):
        server.shell(
            name="Generate self-signed TLS certificate if not present",
            commands=[
                f"[ -f {self.cert_path} ] || openssl req -x509 -newkey rsa:4096"
                f" -nodes -days 3650"
                f" -keyout {self.key_path}"
                f" -out {self.cert_path}"
                f' -subj "/CN={self.mail_domain}"'
                f' -addext "subjectAltName=DNS:{self.mail_domain},DNS:www.{self.mail_domain},DNS:mta-sts.{self.mail_domain}"',
            ],
        )

    def activate(self):
        pass
