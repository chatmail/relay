
from pyinfra import host
from pyinfra.facts.files import File
from pyinfra.operations import systemd

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

        self.put_template(
            "external/tls-cert-reload.path.j2",
            "/etc/systemd/system/tls-cert-reload.path",
            cert_path=self.cert_path,
        )
        self.put_file(
            "external/tls-cert-reload.service",
            "/etc/systemd/system/tls-cert-reload.service",
        )

    def activate(self):
        systemd.service(
            name="Setup tls-cert-reload path watcher",
            service="tls-cert-reload.path",
            running=self.enabled,
            enabled=self.enabled,
            restarted=self.need_restart,
            daemon_reload=self.daemon_reload,
        )
        if not self.enabled:
            systemd.service(
                name="Stop tls-cert-reload.service",
                service="tls-cert-reload.service",
                running=False,
                enabled=False,
                daemon_reload=False,
            )


