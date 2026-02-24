import os
import urllib.request

from pyinfra import host
from pyinfra.facts.server import Arch, Sysctl
from pyinfra.facts.systemd import SystemdEnabled
from pyinfra.operations import apt, files, server, systemd

from cmdeploy.basedeploy import (
    Deployer,
    activate_remote_units,
    configure_remote_units,
    has_systemd,
)


class DovecotDeployer(Deployer):
    def __init__(self, config, disable_mail):
        super().__init__()
        self.config = config
        self.disable_mail = disable_mail
        self.units = ["doveauth"]

    def install(self):
        arch = host.get_fact(Arch)
        if has_systemd() and "dovecot.service" in host.get_fact(SystemdEnabled):
            return  # already installed and running
        _install_dovecot_package("core", arch)
        _install_dovecot_package("imapd", arch)
        _install_dovecot_package("lmtpd", arch)

    def configure(self):
        configure_remote_units(self.config.mail_domain, self.units)

        self.put_template(
            "dovecot/dovecot.conf.j2",
            "/etc/dovecot/dovecot.conf",
            config=self.config,
            debug=False,
            disable_ipv6=self.config.disable_ipv6,
        )
        self.put_file("dovecot/auth.conf", "/etc/dovecot/auth.conf")
        self.put_file(
            "dovecot/push_notification.lua", "/etc/dovecot/push_notification.lua"
        )

        _configure_inotify_limits()

        self.ensure_line(
            name="Set TZ environment variable",
            path="/etc/environment",
            line="TZ=:/etc/localtime",
        )

        self.put_file(
            "service/10_restart_on_failure.conf",
            "/etc/systemd/system/dovecot.service.d/10_restart.conf",
        )

        # Validate dovecot configuration before restart
        if self.need_restart:
            server.shell(
                name="Validate dovecot configuration",
                commands=["doveconf -n >/dev/null"],
            )

    def activate(self):
        activate_remote_units(self.units)

        restart = False if self.disable_mail else self.need_restart

        systemd.service(
            name="Disable dovecot for now"
            if self.disable_mail
            else "Start and enable Dovecot",
            service="dovecot.service",
            running=False if self.disable_mail else True,
            enabled=False if self.disable_mail else True,
            restarted=restart,
            daemon_reload=self.daemon_reload,
        )
        self.need_restart = False


def _pick_url(primary, fallback):
    try:
        req = urllib.request.Request(primary, method="HEAD")
        urllib.request.urlopen(req, timeout=10)
        return primary
    except Exception:
        return fallback


def _configure_inotify_limits():
    # as per https://doc.dovecot.org/2.3/configuration_manual/os/
    # it is recommended to set the following inotify limits
    if not os.environ.get("CHATMAIL_NOSYSCTL"):
        for name in ("max_user_instances", "max_user_watches"):
            key = f"fs.inotify.{name}"
            if host.get_fact(Sysctl)[key] > 65535:
                # Skip updating limits if already sufficient
                # (enables running in incus containers where sysctl readonly)
                continue
            server.sysctl(
                name=f"Change {key}",
                key=key,
                value=65535,
                persist=True,
            )


def _install_dovecot_package(package: str, arch: str):
    arch = "amd64" if arch == "x86_64" else arch
    arch = "arm64" if arch == "aarch64" else arch
    primary_url = f"https://download.delta.chat/dovecot/dovecot-{package}_2.3.21%2Bdfsg1-3_{arch}.deb"
    fallback_url = f"https://github.com/chatmail/dovecot/releases/download/upstream%2F2.3.21%2Bdfsg1/dovecot-{package}_2.3.21%2Bdfsg1-3_{arch}.deb"
    url = _pick_url(primary_url, fallback_url)
    deb_filename = "/root/" + url.rsplit("/", maxsplit=1)[-1]

    match (package, arch):
        case ("core", "amd64"):
            sha256 = "dd060706f52a306fa863d874717210b9fe10536c824afe1790eec247ded5b27d"
        case ("core", "arm64"):
            sha256 = "e7548e8a82929722e973629ecc40fcfa886894cef3db88f23535149e7f730dc9"
        case ("imapd", "amd64"):
            sha256 = "8d8dc6fc00bbb6cdb25d345844f41ce2f1c53f764b79a838eb2a03103eebfa86"
        case ("imapd", "arm64"):
            sha256 = "178fa877ddd5df9930e8308b518f4b07df10e759050725f8217a0c1fb3fd707f"
        case ("lmtpd", "amd64"):
            sha256 = "2f69ba5e35363de50962d42cccbfe4ed8495265044e244007d7ccddad77513ab"
        case ("lmtpd", "arm64"):
            sha256 = "89f52fb36524f5877a177dff4a713ba771fd3f91f22ed0af7238d495e143b38f"
        case _:
            apt.packages(packages=[f"dovecot-{package}"])
            return

    files.download(
        name=f"Download dovecot-{package}",
        src=url,
        dest=deb_filename,
        sha256sum=sha256,
        cache_time=60 * 60 * 24 * 365 * 10,  # never redownload the package
    )

    apt.deb(name=f"Install dovecot-{package}", src=deb_filename)
