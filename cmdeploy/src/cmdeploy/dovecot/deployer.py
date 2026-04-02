import io
import os
import urllib.request

from chatmaild.config import Config
from pyinfra import host
from pyinfra.facts.deb import DebPackages
from pyinfra.facts.server import Arch, Sysctl
from pyinfra.operations import apt, files, server, systemd

from cmdeploy.basedeploy import (
    Deployer,
    activate_remote_units,
    blocked_service_startup,
    configure_remote_units,
    get_resource,
)

DOVECOT_ARCHIVE_VERSION = "2.3.21+dfsg1-3"
DOVECOT_PACKAGE_VERSION = f"1:{DOVECOT_ARCHIVE_VERSION}"

DOVECOT_SHA256 = {
    ("core", "amd64"): "dd060706f52a306fa863d874717210b9fe10536c824afe1790eec247ded5b27d",
    ("core", "arm64"): "e7548e8a82929722e973629ecc40fcfa886894cef3db88f23535149e7f730dc9",
    ("imapd", "amd64"): "8d8dc6fc00bbb6cdb25d345844f41ce2f1c53f764b79a838eb2a03103eebfa86",
    ("imapd", "arm64"): "178fa877ddd5df9930e8308b518f4b07df10e759050725f8217a0c1fb3fd707f",
    ("lmtpd", "amd64"): "2f69ba5e35363de50962d42cccbfe4ed8495265044e244007d7ccddad77513ab",
    ("lmtpd", "arm64"): "89f52fb36524f5877a177dff4a713ba771fd3f91f22ed0af7238d495e143b38f",
}


class DovecotDeployer(Deployer):
    daemon_reload = False

    def __init__(self, config, disable_mail):
        self.config = config
        self.disable_mail = disable_mail
        self.units = ["doveauth"]

    def install(self):
        arch = host.get_fact(Arch)
        with blocked_service_startup():
            debs = []
            for pkg in ("core", "imapd", "lmtpd"):
                deb, changed = _download_dovecot_package(pkg, arch)
                self.need_restart |= changed
                if deb:
                    debs.append(deb)
            if debs:
                deb_list = " ".join(debs)
                server.shell(
                    name="Install dovecot packages",
                    commands=[
                        f"dpkg --force-confdef --force-confold -i {deb_list} 2> /dev/null || true",
                        "DEBIAN_FRONTEND=noninteractive apt-get -y --fix-broken install",
                        f"dpkg --force-confdef --force-confold -i {deb_list}",
                    ],
                )
                self.need_restart = True
        files.put(
            name="Pin dovecot packages to block Debian dist-upgrades",
            src=io.StringIO(
                "Package: dovecot-*\n"
                "Pin: version *\n"
                "Pin-Priority: -1\n"
            ),
            dest="/etc/apt/preferences.d/pin-dovecot",
        )

    def configure(self):
        configure_remote_units(self.config.mail_domain, self.units)
        nr, self.daemon_reload = _configure_dovecot(self.config)
        self.need_restart |= nr

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


def _download_dovecot_package(package: str, arch: str) -> tuple[str | None, bool]:
    """Download a dovecot .deb if needed, return (path, changed)."""
    arch = "amd64" if arch == "x86_64" else arch
    arch = "arm64" if arch == "aarch64" else arch

    pkg_name = f"dovecot-{package}"
    sha256 = DOVECOT_SHA256.get((package, arch))
    if sha256 is None:
        op = apt.packages(packages=[pkg_name])
        return None, bool(getattr(op, "changed", False))

    installed_versions = host.get_fact(DebPackages).get(pkg_name, [])
    if DOVECOT_PACKAGE_VERSION in installed_versions:
        return None, False

    url_version = DOVECOT_ARCHIVE_VERSION.replace("+", "%2B")
    deb_base = f"{pkg_name}_{url_version}_{arch}.deb"
    primary_url = f"https://download.delta.chat/dovecot/{deb_base}"
    fallback_url = f"https://github.com/chatmail/dovecot/releases/download/upstream%2F{url_version}/{deb_base}"
    url = _pick_url(primary_url, fallback_url)
    deb_filename = f"/root/{deb_base}"

    files.download(
        name=f"Download {pkg_name}",
        src=url,
        dest=deb_filename,
        sha256sum=sha256,
        cache_time=60 * 60 * 24 * 365 * 10,  # never redownload the package
    )

    return deb_filename, True


def _configure_dovecot(config: Config, debug: bool = False) -> (bool, bool):
    """Configures Dovecot IMAP server."""
    need_restart = False
    daemon_reload = False

    main_config = files.template(
        src=get_resource("dovecot/dovecot.conf.j2"),
        dest="/etc/dovecot/dovecot.conf",
        user="root",
        group="root",
        mode="644",
        config=config,
        debug=debug,
        disable_ipv6=config.disable_ipv6,
    )
    need_restart |= main_config.changed
    auth_config = files.put(
        src=get_resource("dovecot/auth.conf"),
        dest="/etc/dovecot/auth.conf",
        user="root",
        group="root",
        mode="644",
    )
    need_restart |= auth_config.changed
    lua_push_notification_script = files.put(
        src=get_resource("dovecot/push_notification.lua"),
        dest="/etc/dovecot/push_notification.lua",
        user="root",
        group="root",
        mode="644",
    )
    need_restart |= lua_push_notification_script.changed

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

    timezone_env = files.line(
        name="Set TZ environment variable",
        path="/etc/environment",
        line="TZ=:/etc/localtime",
    )
    need_restart |= timezone_env.changed

    restart_conf = files.put(
        name="dovecot: restart automatically on failure",
        src=get_resource("service/10_restart.conf"),
        dest="/etc/systemd/system/dovecot.service.d/10_restart.conf",
    )
    daemon_reload |= restart_conf.changed

    # Validate dovecot configuration before restart
    if need_restart:
        server.shell(
            name="Validate dovecot configuration",
            commands=["doveconf -n >/dev/null"],
        )

    return need_restart, daemon_reload
