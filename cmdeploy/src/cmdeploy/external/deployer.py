
from pyinfra import host
from pyinfra.facts.files import File

from ..basedeploy import Deployer


class ExternalTlsDeployer(Deployer):
    """Expects TLS certificates to be managed on the server.

    Validates that the configured certificate and key files
    exist on the remote host.  Installs a systemd path unit
    that watches the certificate file and automatically
    restarts/reloads affected services when it changes.
    """

    def __init__(self, cert_path, key_path):
        self.cert_path = cert_path
        self.key_path = key_path

    def configure(self):
        # Verify cert and key exist on the remote host using pyinfra facts.
        for path in (self.cert_path, self.key_path):
                if host.get_fact(File, path=path) is None:
                    raise Exception(f"External TLS file not found on server: {path}")

        self.ensure_systemd_unit(
            "external/tls-cert-reload.path.j2",
            cert_path=self.cert_path,
        )
        self.ensure_systemd_unit(
            "external/tls-cert-reload.service",
        )

    def activate(self):
        # No explicit reload needed here: dovecot/nginx read the cert
        # on startup, and the .path watcher handles live changes.
        self.ensure_service(
            "tls-cert-reload.path",
            running=True,
            enabled=True,
        )


