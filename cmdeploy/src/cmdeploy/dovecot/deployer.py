from chatmaild.config import Config
from pyinfra import host
from pyinfra.facts.server import Arch, LinuxDistribution, Sysctl
from pyinfra.facts.systemd import SystemdEnabled
from pyinfra.operations import apt, files, server, systemd

from cmdeploy.basedeploy import (
    Deployer,
    activate_remote_units,
    configure_remote_units,
    get_resource,
)


class DovecotDeployer(Deployer):
    daemon_reload = False

    def __init__(self, config, disable_mail):
        self.config = config
        self.disable_mail = disable_mail
        self.units = ["doveauth"]

    def install(self):
        arch = host.get_fact(Arch)
        if not "dovecot.service" in host.get_fact(SystemdEnabled):
            _install_dovecot_package("core", arch)
            _install_dovecot_package("imapd", arch)
            _install_dovecot_package("lmtpd", arch)

    def configure(self):
        configure_remote_units(self.config.mail_domain, self.units)
        self.need_restart, self.daemon_reload = _configure_dovecot(self.config)

    def activate(self):
        activate_remote_units(self.units)

        restart = False if self.disable_mail else self.need_restart

        systemd.service(
            name="disable dovecot for now"
            if self.disable_mail
            else "Start and enable Dovecot",
            service="dovecot.service",
            running=False if self.disable_mail else True,
            enabled=False if self.disable_mail else True,
            restarted=restart,
            daemon_reload=self.daemon_reload,
        )
        self.need_restart = False


def _install_dovecot_package(package: str, arch: str):
    distro = host.get_fact(LinuxDistribution)
    is_old_debian = False
    if distro:
        distro_id = str(distro.get("id", "")).lower()
        distro_name = str(distro.get("name", "")).lower()
        major_version = str(distro.get("major_version", "0"))
        
        if "debian" in distro_id or "debian" in distro_name:
            try:
                # Handle cases where major_version might be '11.13'
                m_ver = major_version.split(".")[0]
                if m_ver.isdigit() and 0 < int(m_ver) < 12:
                    is_old_debian = True
            except (ValueError, TypeError, IndexError):
                pass
        # Fallback for systems where major_version might not be parsed correctly but name contains 'bullseye'
        if "bullseye" in distro_name or "buster" in distro_name:
            is_old_debian = True

    if is_old_debian:
        apt.packages(
            name=f"Install system dovecot-{package}",
            packages=[f"dovecot-{package}"],
            update=True,
        )
        return

    arch = "amd64" if arch == "x86_64" else arch
    arch = "arm64" if arch == "aarch64" else arch
    url = f"https://download.delta.chat/dovecot/dovecot-{package}_2.3.21%2Bdfsg1-3_{arch}.deb"
    deb_filename = "/root/" + url.split("/")[-1]

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

    # Use a shell command to try installing the custom .deb and fallback if it fails.
    # This prevents the whole deployment from failing if custom dovecot is not compatible.
    server.shell(
        name=f"Install dovecot-{package} (custom or system fallback)",
        commands=[
            f"if ! dpkg -i {deb_filename}; then "
            f"echo 'HEY: dovecot the custom is not installed, we install your os main one' >&2; "
            f"DEBIAN_FRONTEND=noninteractive apt-get install -f -y; "
            f"DEBIAN_FRONTEND=noninteractive apt-get install -y dovecot-{package}; "
            f"fi"
        ],
    )


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

    # as per https://doc.dovecot.org/configuration_manual/os/
    # it is recommended to set the following inotify limits
    try:
        sysctls = host.get_fact(Sysctl)
    except Exception:
        sysctls = None

    if sysctls:
        for name in ("max_user_instances", "max_user_watches"):
            key = f"fs.inotify.{name}"
            if sysctls.get(key, 0) > 65535:
                # Skip updating limits if already sufficient
                # (enables running in incus containers where sysctl readonly)
                continue
            server.sysctl(
                name=f"Change {key}",
                key=key,
                value=65535,
                persist=True,
                _ignore_errors=True,
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

    return need_restart, daemon_reload
