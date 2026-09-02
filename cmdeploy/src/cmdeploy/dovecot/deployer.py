import urllib.request

from chatmaild.config import Config
from pyinfra import host
from pyinfra.facts.deb import DebPackages
from pyinfra.facts.server import Arch, Command, Sysctl
from pyinfra.operations import files, server

from cmdeploy.basedeploy import (
    Deployer,
    activate_remote_units,
    blocked_service_startup,
    configure_remote_units,
    is_in_container,
)
from cmdeploy.pins import DOVECOT_SHA256, DOVECOT_VERSION

VERSION_ID_CMD = "grep '^VERSION_ID=' /etc/os-release"


def _stamped_version(deb_release: int) -> str:
    """Version as built, including the per-distro suffix stamped by
    chatmail/dovecot CI into package version and filename."""
    return f"{DOVECOT_VERSION}+deb{deb_release}u1"


class DovecotDeployer(Deployer):
    daemon_reload = False

    def __init__(self, config, disable_mail):
        self.config = config
        self.disable_mail = disable_mail
        self.units = []

    def install(self):
        arch = host.get_fact(Arch)
        deb_release = _parse_version_id(host.get_fact(Command, VERSION_ID_CMD))
        with blocked_service_startup():
            debs = []
            for pkg in ("core", "imapd", "lmtpd", "auth-lua"):
                deb, changed = _download_dovecot_package(pkg, arch, deb_release)
                self.need_restart |= changed
                if deb:
                    debs.append(deb)
            if debs:
                deb_list = " ".join(debs)
                # apt-get install with local .deb paths resolves depends
                # against the configured repos (e.g. pulls libwrap0),
                # The pin file written earlier by ChatmailDeployer prevents apt
                # from installing a 'wrong' version
                server.shell(
                    name="Install dovecot packages",
                    commands=[
                        "DEBIAN_FRONTEND=noninteractive apt-get install -y "
                        '-o Dpkg::Options::="--force-confdef" '
                        '-o Dpkg::Options::="--force-confold" '
                        f"--allow-downgrades {deb_list}",
                    ],
                )
                self.need_restart = True

    def configure(self):
        configure_remote_units(self, self.config.mail_domain_bare, self.units)
        _configure_dovecot(self, self.config)

    def activate(self):
        activate_remote_units(self, self.units)

        # Detect stale binary: package installed but service still runs old (deleted) binary.
        if not self.disable_mail and not self.need_restart:
            stale = host.get_fact(
                Command,
                "pid=$(systemctl show -p MainPID --value dovecot.service 2>/dev/null);"
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


def _parse_version_id(version_line: str) -> int:
    """Debian major release from an /etc/os-release VERSION_ID line."""
    _, _, raw = (version_line or "").strip().partition("=")
    try:
        return int(raw.strip('"'))
    except ValueError:
        raise ValueError(f"cannot determine Debian release from {version_line!r}")


def _pick_url(primary, fallback):
    try:
        req = urllib.request.Request(primary, method="HEAD")
        urllib.request.urlopen(req, timeout=10)
        return primary
    except Exception:
        return fallback


def _download_dovecot_package(package: str, arch: str, deb_release: int) -> tuple[str | None, bool]:
    """Download a dovecot .deb if needed, return (path, changed)."""
    arch = "amd64" if arch == "x86_64" else arch
    arch = "arm64" if arch == "aarch64" else arch

    pkg_name = f"dovecot-{package}"
    try:
        # never fall back to the distro package: it is pinned to -1 and would
        # in any case be a version we did not build and do not support
        sha256 = DOVECOT_SHA256[(arch, deb_release, package)]
    except KeyError:
        raise ValueError(f"no dovecot build for {pkg_name} on deb{deb_release}/{arch}")

    stamped_version = _stamped_version(deb_release)
    installed_versions = host.get_fact(DebPackages).get(pkg_name, [])
    if f"1:{stamped_version}" in installed_versions:
        return None, False

    # Primary URL: flat structure with distro suffix in filename
    primary_deb = f"{pkg_name}_{stamped_version}_{arch}.deb"
    primary_url = f"https://download.delta.chat/dovecot/{primary_deb}"
    # GitHub release files: escaped + in filename; the release tag stays
    # distro-neutral, both distros ship in one combined release
    tag_version = DOVECOT_VERSION.replace("+", "%2B")
    fallback_deb = f"{pkg_name}_{stamped_version.replace('+', '%2B')}_{arch}.deb"
    fallback_url = (
        f"https://github.com/chatmail/dovecot/releases/download/upstream%2F{tag_version}/{fallback_deb}"
    )
    url = _pick_url(primary_url, fallback_url)
    deb_filename = f"/root/{primary_deb}"

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
    deployer.put_template("dovecot/auth.lua.j2", "/etc/dovecot/auth.lua", config=config)
    deployer.remove_file("/etc/dovecot/auth.conf")
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
