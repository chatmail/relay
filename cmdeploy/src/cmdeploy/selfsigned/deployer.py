import shlex

from pyinfra.operations import apt, server

from cmdeploy.basedeploy import Deployer


def openssl_selfsigned_args(domain, cert_path, key_path, days=36500):
    """Return the openssl argument list for a self-signed certificate.

    The certificate uses an EC P-256 key with SAN entries for *domain*,
    ``www.<domain>`` and ``mta-sts.<domain>``.
    """
    return [
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "ec",
        "-pkeyopt",
        "ec_paramgen_curve:P-256",
        "-noenc",
        "-days",
        str(days),
        "-keyout",
        str(key_path),
        "-out",
        str(cert_path),
        "-subj",
        f"/CN={domain}",
        "-addext",
        "extendedKeyUsage=serverAuth,clientAuth",
        "-addext",
        f"subjectAltName=DNS:{domain},DNS:www.{domain},DNS:mta-sts.{domain}",
    ]


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
        args = openssl_selfsigned_args(
            self.mail_domain,
            self.cert_path,
            self.key_path,
        )
        cmd = shlex.join(args)
        server.shell(
            name="Generate self-signed TLS certificate if not present",
            commands=[f"[ -f {self.cert_path} ] || {cmd}"],
        )

    def activate(self):
        pass
