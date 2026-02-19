from pyinfra.operations import files, server, systemd

from cmdeploy.basedeploy import Deployer, get_resource


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
        server.shell(
            name="Verify external TLS certificate and key exist",
            commands=[
                f"test -f {self.cert_path} && test -f {self.key_path}",
            ],
        )

        # Deploy the .path unit (templated with the cert path).
        source = get_resource("tls-cert-reload.path.f", pkg=__package__)
        content = source.read_text().format(cert_path=self.cert_path).encode()

        import io

        path_unit = files.put(
            name="Upload tls-cert-reload.path",
            src=io.BytesIO(content),
            dest="/etc/systemd/system/tls-cert-reload.path",
            user="root",
            group="root",
            mode="644",
        )

        service_unit = files.put(
            name="Upload tls-cert-reload.service",
            src=get_resource("tls-cert-reload.service", pkg=__package__),
            dest="/etc/systemd/system/tls-cert-reload.service",
            user="root",
            group="root",
            mode="644",
        )

        if path_unit.changed or service_unit.changed:
            self.need_restart = True

    def activate(self):
        systemd.service(
            name="Enable tls-cert-reload path watcher",
            service="tls-cert-reload.path",
            running=True,
            enabled=True,
            restarted=self.need_restart,
            daemon_reload=self.need_restart,
        )
        # Always trigger a reload so services pick up the current cert.
        # The path unit handles future changes via inotify.
        server.shell(
            name="Reload TLS services for current certificate",
            commands=["systemctl start tls-cert-reload.service"],
        )

