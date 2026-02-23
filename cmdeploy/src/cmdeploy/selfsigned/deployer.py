import importlib.resources
import shlex

from pyinfra.operations import files, server

from ..basedeploy import Deployer

_acmetool_res = importlib.resources.files("cmdeploy.tls.acmetool")
_external_res = importlib.resources.files("cmdeploy.tls.external")


def openssl_selfsigned_args(domain, cert_path, key_path, days=36500):
    """Return the openssl argument list for a self-signed certificate.

    The certificate uses an EC P-256 key with SAN entries for *domain*,
    ``www.<domain>`` and ``mta-sts.<domain>``.
    """
    return [
        "openssl", "req", "-x509",
        "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
        "-noenc", "-days", str(days),
        "-keyout", str(key_path),
        "-out", str(cert_path),
        "-subj", f"/CN={domain}",
        # Mark as end-entity cert so it cannot be used as a CA to sign others.
        "-addext", "basicConstraints=critical,CA:FALSE",
        "-addext", "extendedKeyUsage=serverAuth,clientAuth",
        "-addext",
        f"subjectAltName=DNS:{domain},DNS:www.{domain},DNS:mta-sts.{domain}",
    ]


class SelfSignedTlsDeployer(Deployer):
    """Generates a self-signed TLS certificate for all chatmail endpoints."""

    def __init__(self, mail_domain):
        self.mail_domain = mail_domain
        self.cert_path = "/etc/ssl/certs/mailserver.pem"
        self.key_path = "/etc/ssl/private/mailserver.key"



    def configure(self):
        if self.enabled:
            args = openssl_selfsigned_args(
                self.mail_domain, self.cert_path, self.key_path,
            )
            cmd = shlex.join(args)
            server.shell(
                name="Generate self-signed TLS certificate if not present",
                commands=[f"[ -f {self.cert_path} ] || {cmd}"],
            )
        else:
            files.file(
                name="Remove self-signed TLS certificate",
                path=self.cert_path,
                present=False,
            )
            files.file(
                name="Remove self-signed TLS private key",
                path=self.key_path,
                present=False,
            )

    def activate(self):
        pass


