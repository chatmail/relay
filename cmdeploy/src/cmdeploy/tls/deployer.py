"""TLS certificate deployers for chatmail.

Each deployer handles a different certificate management strategy
(ACME, external, or self-signed) and supports an ``enabled`` flag
so that inactive modes can cleanly un-deploy their resources.
"""

import importlib.resources
import io
import shlex

from pyinfra import host
from pyinfra.facts.files import File
from pyinfra.operations import apt, files, server, systemd

from ..basedeploy import Deployer

_acmetool_res = importlib.resources.files("cmdeploy.tls.acmetool")
_external_res = importlib.resources.files("cmdeploy.tls.external")

# ---------------------------------------------------------------------------
#  ACME (Let's Encrypt via acmetool)
# ---------------------------------------------------------------------------


class AcmetoolDeployer(Deployer):
    services = [
        # (basename, is_active, restart_type)
        ("acmetool-redirector.service", True, "restarted"),
        ("acmetool-reconcile.service", False, "daemon_reload"),
        ("acmetool-reconcile.timer", True, "daemon_reload"),
    ]

    def __init__(self, mode, email, domains):
        self.enabled = mode == "acme"
        self.domains = domains
        self.email = email
        self.service_changed = {s[0]: False for s in self.services}

    def remove_legacy_files(self):
        files.file(
            name="Remove old acmetool cronjob",
            path="/etc/cron.d/acmetool",
            present=False,
        )
        files.file(
            name="Remove acmetool hook from wrong location",
            path="/usr/lib/acme/hooks/nginx",
            present=False,
        )

    def install(self):
        self.remove_legacy_files()
        apt.packages(
            name="Install acmetool" if self.enabled else "Remove acmetool",
            packages=["acmetool"],
            present=self.enabled,
        )
        self.put_file(
            name="Deploy acmetool hook",
            dest="/etc/acme/hooks/nginx",
            src=_acmetool_res.joinpath("acmetool.hook").open("rb"),
            executable=True,
        )

    def configure(self):
        if self.enabled:
            server.shell(
                name=f"Remove old acmetool desired files for {self.domains[-1]}",
                commands=[f"rm -f /var/lib/acme/desired/{self.domains[-1]}-*"],
            )

        setup_targets = [
            (
                "Setup acmetool responses",
                "response-file.yaml.j2",
                "/var/lib/acme/conf/responses",
            ),
            (
                "Setup acmetool target",
                "target.yaml.j2",
                "/var/lib/acme/conf/target",
            ),
            (
                f"Setup acmetool desired domains for {self.domains[0]}",
                "desired.yaml.j2",
                f"/var/lib/acme/desired/{self.domains[0]}",
            ),
        ]

        for name, src, dest in setup_targets:
            self.put_template(
                name=name,
                src=_acmetool_res.joinpath(src),
                dest=dest,
                email=self.email,
                domains=self.domains,
            )

        for basename, _, _ in self.services:
            res = self.put_file(
                name=f"Setup {basename}",
                src=_acmetool_res.joinpath(basename),
                dest=f"/etc/systemd/system/{basename}",
            )
            # Track if unit file changed so activate() knows to restart/reload.
            self.service_changed[basename] = res.changed

    def activate(self):
        for basename, is_active, restart_type in self.services:
            is_enabled = self.enabled and is_active
            kwargs = {
                "name": f"Setup {basename}",
                "service": basename,
                "running": is_enabled,
                "enabled": is_enabled,
            }
            # Some services need 'restarted=True', others only 'daemon_reload=True'
            kwargs[restart_type] = self.service_changed[basename]
            systemd.service(**kwargs)
            self.service_changed[basename] = False

        if self.enabled:
            server.shell(
                name=f"Reconcile certificates for: {', '.join(self.domains)}",
                commands=["acmetool --batch --xlog.severity=debug reconcile"],
            )


# ---------------------------------------------------------------------------
#  External TLS (certificates managed outside chatmail)
# ---------------------------------------------------------------------------


class ExternalTlsDeployer(Deployer):
    """Watches externally managed certificate files and reloads services."""

    def __init__(self, mode, cert_path, key_path):
        self.enabled = mode == "external"
        self.cert_path = cert_path
        self.key_path = key_path

    def configure(self):
        if self.enabled:
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
        # No explicit reload needed here: dovecot/nginx read the cert
        # on startup, and the .path watcher handles live changes.
        if not self.enabled:
            systemd.service(
                name="Stop tls-cert-reload.service",
                service="tls-cert-reload.service",
                running=False,
                enabled=False,
                daemon_reload=False,
            )


# ---------------------------------------------------------------------------
#  Self-signed TLS
# ---------------------------------------------------------------------------


class SelfSignedTlsDeployer(Deployer):
    """Generates a self-signed TLS certificate for all chatmail endpoints."""

    def __init__(self, mode, mail_domain):
        self.enabled = mode == "self"
        self.mail_domain = mail_domain
        self.cert_path = "/etc/ssl/certs/mailserver.pem"
        self.key_path = "/etc/ssl/private/mailserver.key"

    def create_key_command(self):
        return shlex.join(
            [
                "openssl", "req", "-x509",
                "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
                "-noenc", "-days", "36500",
                "-keyout", self.key_path,
                "-out", self.cert_path,
                "-subj", f"/CN={self.mail_domain}",
                "-addext", "extendedKeyUsage=serverAuth,clientAuth",
                "-addext",
                f"subjectAltName=DNS:{self.mail_domain},"
                f"DNS:www.{self.mail_domain},"
                f"DNS:mta-sts.{self.mail_domain}",
            ]
        )

    def configure(self):
        if self.enabled:
            cmd = self.create_key_command()
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


# ---------------------------------------------------------------------------
#  Factory
# ---------------------------------------------------------------------------


def get_tls_deployers(config, mail_domain):
    """Return all TLS deployers with their enabled state set."""
    tls_domains = [mail_domain, f"mta-sts.{mail_domain}", f"www.{mail_domain}"]
    return [
        AcmetoolDeployer(config.tls_cert_mode, config.acme_email, tls_domains),
        SelfSignedTlsDeployer(config.tls_cert_mode, mail_domain),
        ExternalTlsDeployer(
            config.tls_cert_mode,
            config.tls_cert_path,
            config.tls_key_path,
        ),
    ]
