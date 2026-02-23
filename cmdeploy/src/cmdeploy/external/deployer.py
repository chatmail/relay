import importlib.resources
import io
import shlex

from pyinfra import host
from pyinfra.facts.files import File
from pyinfra.operations import apt, files, server, systemd

from ..basedeploy import Deployer

_acmetool_res = importlib.resources.files("cmdeploy.tls.acmetool")
_external_res = importlib.resources.files("cmdeploy.tls.external")


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

            source = _external_res.joinpath("tls-cert-reload.path.f")
            content = source.read_text().format(cert_path=self.cert_path).encode()
            path_src = io.BytesIO(content)
            service_src = _external_res.joinpath("tls-cert-reload.service")
        else:
            path_src = service_src = None

        self.put_file(
            name="Setup tls-cert-reload.path",
            src=path_src,
            dest="/etc/systemd/system/tls-cert-reload.path",
        )
        self.put_file(
            name="Setup tls-cert-reload.service",
            src=service_src,
            dest="/etc/systemd/system/tls-cert-reload.service",
        )

    def activate(self):
        systemd.service(
            name="Setup tls-cert-reload path watcher",
            service="tls-cert-reload.path",
            running=self.enabled,
            enabled=self.enabled,
            restarted=self.need_restart,
            daemon_reload=self.need_restart,
        )
        if not self.enabled:
            systemd.service(
                name="Stop tls-cert-reload.service",
                service="tls-cert-reload.service",
                running=False,
                enabled=False,
                daemon_reload=False,
            )


