import shlex
from pathlib import Path

from chatmaild.config import read_config
from pyinfra.operations import apt, files, server

CHATMAIL_UNITS = [
    "doveauth.service",
    "lastlogin.service",
    "chatmail-metadata.service",
    "chatmail-expire.service",
    "chatmail-expire.timer",
    "chatmail-fsreport.service",
    "chatmail-fsreport.timer",
    "filtermail.service",
    "filtermail-incoming.service",
    "filtermail-transport.service",
    "turnserver.service",
    "iroh-relay.service",
    "mtail.service",
    "acmetool-redirector.service",
    "acmetool-reconcile.service",
    "acmetool-reconcile.timer",
    "tls-cert-reload.path",
    "tls-cert-reload.service",
]

LEGACY_UNITS = [
    "doveauth-dictproxy.service",
    "echobot.service",
    "mta-sts-daemon.service",
]

PACKAGE_UNITS = [
    "dovecot.service",
    "postfix.service",
    "nginx.service",
    "opendkim.service",
    "unbound.service",
    "fcgiwrap.service",
]

PACKAGE_NAMES = [
    "acmetool",
    "dovecot-core",
    "dovecot-imapd",
    "dovecot-lmtpd",
    "postfix",
    "opendkim",
    "opendkim-tools",
    "nginx",
    "nginx-common",
    "libnginx-mod-stream",
    "fcgiwrap",
    "unbound",
    "unbound-anchor",
    "dnsutils",
    "python3-virtualenv",
    "gcc",
    "python3-dev",
    "curl",
    "rsync",
]

RELAY_FILES = [
    "/etc/apt/apt.conf.d/00InstallRecommends",
    "/etc/apt/keyrings/obs-home-deltachat.gpg",
    "/etc/apt/preferences.d/pin-dovecot",
    "/etc/chatmail-nocreate",
    "/etc/chatmail-version",
    "/etc/cron.d/acmetool",
    "/etc/cron.d/chatmail-metrics",
    "/etc/cron.d/expunge",
    "/etc/dovecot/auth.conf",
    "/etc/dovecot/dovecot.conf",
    "/etc/dovecot/push_notification.lua",
    "/etc/iroh-relay.toml",
    "/etc/mailname",
    "/etc/mta-sts-daemon.yml",
    "/etc/mtail/delivered_mail.mtail",
    "/etc/nginx/nginx.conf",
    "/etc/opendkim.conf",
    "/etc/postfix/lmtp_header_cleanup",
    "/etc/postfix/login_map",
    "/etc/postfix/main.cf",
    "/etc/postfix/master.cf",
    "/etc/postfix/smtp_tls_policy_map",
    "/etc/postfix/smtp_tls_policy_map.db",
    "/etc/postfix/submission_header_cleanup",
    "/etc/systemd/journald.conf",
    "/etc/systemd/system/mta-sts-daemon.service",
    "/etc/systemd/system/dovecot.service.d/10_restart.conf",
    "/etc/systemd/system/opendkim.service.d/10-prevent-memory-leak.conf",
    "/etc/systemd/system/postfix@.service.d/10_restart.conf",
    "/etc/unbound/unbound.conf.d/chatmail.conf",
    "/usr/lib/cgi-bin/newemail.py",
    "/usr/local/bin/chatmail-turn",
    "/usr/local/bin/filtermail",
    "/usr/local/bin/iroh-relay",
    "/usr/local/bin/mtail",
    "/usr/sbin/policy-rc.d",
    "/var/www/html/metrics",
]

PACKAGE_CONFIG_DIRS = [
    "/etc/dkimkeys",
    "/etc/dovecot",
    "/etc/nginx",
    "/etc/opendkim",
    "/etc/postfix",
    "/etc/unbound",
]

RELAY_DIRS = [
    "/etc/mtail",
    "/root/from-cmdeploy",
    "/usr/local/lib/chatmaild",
    "/usr/local/lib/postfix-mta-sts-resolver",
    "/var/lib/dovecot",
    "/var/lib/nginx",
    "/var/lib/postfix",
    "/var/lib/unbound",
    "/var/log/nginx",
    "/var/spool/postfix",
    "/var/www/html",
]

EMPTY_SYSTEMD_DIRS = [
    "/etc/systemd/system/dovecot.service.d",
    "/etc/systemd/system/opendkim.service.d",
    "/etc/systemd/system/postfix@.service.d",
]

RELAY_USERS = ["vmail", "iroh", "opendkim"]
RELAY_GROUPS = ["vmail", "iroh", "opendkim"]


def _quote(value) -> str:
    return shlex.quote(str(value))


def _systemd_command(args: str) -> str:
    return (
        "if command -v systemctl >/dev/null && [ -d /run/systemd/system ]; "
        f"then systemctl {args} || true; fi"
    )


def _remove_file(path: str):
    files.file(name=f"Remove {path}", path=path, present=False)


def _remove_dir(path: str):
    files.directory(name=f"Remove {path}", path=path, present=False)


def _remove_units():
    units = CHATMAIL_UNITS + LEGACY_UNITS + PACKAGE_UNITS
    quoted_units = " ".join(_quote(unit) for unit in units)
    server.shell(
        name="Stop and disable chatmail services",
        commands=[_systemd_command(f"disable --now {quoted_units}")],
    )

    for unit in CHATMAIL_UNITS + LEGACY_UNITS:
        _remove_file(f"/etc/systemd/system/{unit}")
    for path in RELAY_FILES:
        _remove_file(path)

    dirs = " ".join(_quote(path) for path in EMPTY_SYSTEMD_DIRS)
    server.shell(
        name="Remove empty chatmail systemd drop-in directories",
        commands=[f"rmdir --ignore-fail-on-non-empty {dirs} 2>/dev/null || true"],
    )
    server.shell(
        name="Reload systemd after removing chatmail units",
        commands=[
            _systemd_command("daemon-reload"),
            _systemd_command("reset-failed"),
        ],
    )


def _remove_packages(keep_packages: bool):
    if keep_packages:
        return
    apt.packages(
        name="Purge chatmail relay packages",
        packages=PACKAGE_NAMES,
        present=False,
        purge=True,
    )
    server.shell(
        name="Remove downloaded dovecot packages",
        commands=[
            "rm -f -- /root/dovecot-core_*.deb "
            "/root/dovecot-imapd_*.deb /root/dovecot-lmtpd_*.deb"
        ],
    )


def _remove_dynamic_state(config, keep_packages: bool):
    if not keep_packages:
        for path in PACKAGE_CONFIG_DIRS:
            _remove_dir(path)

    for path in RELAY_DIRS:
        _remove_dir(path)

    _remove_dir(str(config.mailboxes_dir))

    passdb = _quote(config.passdb_path)
    server.shell(
        name="Remove legacy chatmail passdb files",
        commands=[f"rm -f -- {passdb} {passdb}.old {passdb}-*"],
    )

    home_vmail = Path("/home/vmail")
    if home_vmail == config.mailboxes_dir or home_vmail in config.mailboxes_dir.parents:
        _remove_dir(str(home_vmail))

    if config.tls_cert_mode == "self":
        _remove_file("/etc/ssl/certs/mailserver.pem")
        _remove_file("/etc/ssl/private/mailserver.key")
    elif config.tls_cert_mode == "acme":
        _remove_dir("/etc/acme")
        _remove_dir("/var/lib/acme")


def _restore_basic_resolver():
    server.shell(
        name="Restore basic resolver after removing unbound",
        commands=[
            _systemd_command("unmask systemd-resolved.service"),
            _systemd_command("enable --now systemd-resolved.service"),
            "if [ -e /run/systemd/resolve/stub-resolv.conf ]; then "
            "ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf; "
            "else printf 'nameserver 9.9.9.9\\n' >/etc/resolv.conf; fi",
        ],
    )


def _remove_environment_changes():
    files.line(
        name="Remove chatmail TZ environment override",
        path="/etc/environment",
        line="TZ=:/etc/localtime",
        present=False,
    )
    files.line(
        name="Remove chatmail inotify instance sysctl override",
        path="/etc/sysctl.conf",
        line="fs.inotify.max_user_instances = 65535",
        present=False,
    )
    files.line(
        name="Remove chatmail inotify watches sysctl override",
        path="/etc/sysctl.conf",
        line="fs.inotify.max_user_watches = 65535",
        present=False,
    )
    files.line(
        name="Remove legacy chatmail dovecot package repository",
        path="/etc/apt/sources.list",
        line="deb [signed-by=/etc/apt/keyrings/obs-home-deltachat.gpg] https://download.opensuse.org/repositories/home:/deltachat/Debian_12/ ./",
        escape_regex_characters=True,
        present=False,
    )


def _remove_users():
    commands = []
    for user in RELAY_USERS:
        quoted = _quote(user)
        commands.append(f"userdel -r {quoted} 2>/dev/null || userdel {quoted} || true")
    for group in RELAY_GROUPS:
        commands.append(f"groupdel {_quote(group)} 2>/dev/null || true")
    server.shell(name="Remove chatmail users and groups", commands=commands)


def remove_chatmail(config_path: Path, keep_packages: bool = False) -> None:
    """Remove the deployed chatmail relay from the target host."""
    config = read_config(config_path)

    _remove_units()
    _remove_packages(keep_packages=keep_packages)
    _remove_dynamic_state(config, keep_packages=keep_packages)
    _remove_environment_changes()
    _restore_basic_resolver()
    _remove_users()
