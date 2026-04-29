import io
import urllib.request

from chatmaild.config import Config
from pyinfra import host
from pyinfra.facts.deb import DebPackages
from pyinfra.facts.server import Arch, Command, Sysctl
from pyinfra.operations import apt, files, server

from cmdeploy.basedeploy import (
    Deployer,
    activate_remote_units,
    blocked_service_startup,
    configure_remote_units,
    is_in_container,
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
                # First dpkg may fail on missing dependencies (stderr suppressed);
                # apt-get --fix-broken pulls them in, then dpkg retries cleanly.
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
            user="root",
            group="root",
            mode="644",
        )

    def configure(self):
        self.daemon_reload |= configure_remote_units(
            self.config.mail_domain, self.units
        )
        _configure_dovecot(self, self.config)

    def activate(self):
        activate_remote_units(self.units, daemon_reload=self.daemon_reload)

        # Detect stale binary: package installed but service still runs old (deleted) binary.
        if not self.disable_mail and not self.need_restart:
            stale = host.get_fact(
                Command,
                'pid=$(systemctl show -p MainPID --value dovecot.service 2>/dev/null);'
                ' [ "${pid:-0}" != "0" ] && readlink "/proc/$pid/exe" 2>/dev/null | grep -q "(deleted)"'
                " && echo STALE || true",
            )
            if stale == "STALE":
                self.need_restart = True

        active = not self.disable_mail
        self.ensure_service(
            "dovecot.service",
            running=active,
            enabled=active,
        )


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

def _configure_dovecot(deployer, config: Config, debug: bool = False):
    """Configures Dovecot IMAP server."""
    deployer.put_template(
        "dovecot/dovecot.conf.j2",
        "/etc/dovecot/dovecot.conf",
        config=config,
        debug=debug,
        disable_ipv6=config.disable_ipv6,
    )
    deployer.put_file("dovecot/auth.conf", "/etc/dovecot/auth.conf")
    deployer.put_file(
        "dovecot/push_notification.lua", "/etc/dovecot/push_notification.lua"
    )

    # as per https://doc.dovecot.org/2.3/configuration_manual/os/
    # it is recommended to set the following inotify limits
    can_modify = not is_in_container()
    for name in ("max_user_instances", "max_user_watches"):
        key = f"fs.inotify.{name}"
        value = host.get_fact(Sysctl).get(key, 0)
        if value > 65534:
            continue
        if not can_modify:
            print(
                "\n!!!! refusing to attempt sysctl setting in containers\n"
                f"!!!! dovecot: sysctl {key!r}={value}, should be >65534 for production setups\n"
                "!!!!"
            )
            continue
        server.sysctl(
            name=f"Change {key}",
            key=key,
            value=65535,
            persist=True,
        )

    deployer.ensure_line(
        name="Set TZ environment variable",
        path="/etc/environment",
        line="TZ=:/etc/localtime",
    )

    deployer.put_file(
        "service/10_restart_on_failure.conf",
        "/etc/systemd/system/dovecot.service.d/10_restart.conf",
    )

    # Validate dovecot configuration before restart
    if deployer.need_restart:
        server.shell(
            name="Validate dovecot configuration",
            commands=["doveconf -n >/dev/null"],
        )
