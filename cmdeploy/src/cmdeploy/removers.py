import shlex
from pathlib import Path

from chatmaild.config import read_config
from pyinfra.operations import apt, files, server

from cmdeploy.constants import (
    ACME_PATHS,
    BINARY_PATHS,
    CHATMAILD_PATHS,
    CONFIG_DIRS,
    CONFIG_FILES,
    STATE_DIRS,
    TLS_PATHS,
    WEB_PATHS,
)

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
    CONFIG_FILES["apt_install_recommends"],
    CONFIG_FILES["apt_obs_keyring"],
    CONFIG_FILES["apt_pin_dovecot"],
    CONFIG_FILES["chatmail_nocreate"],
    CONFIG_FILES["chatmail_version"],
    CONFIG_FILES["cron_acmetool"],
    CONFIG_FILES["cron_chatmail_metrics"],
    CONFIG_FILES["cron_expunge"],
    CONFIG_FILES["dovecot_auth"],
    CONFIG_FILES["dovecot_conf"],
    CONFIG_FILES["dovecot_push_notification"],
    CONFIG_FILES["iroh_relay"],
    CONFIG_FILES["journald"],
    CONFIG_FILES["mailname"],
    CONFIG_FILES["mtail_program"],
    CONFIG_FILES["mtasts_daemon"],
    CONFIG_FILES["nginx_conf"],
    CONFIG_FILES["opendkim_conf"],
    CONFIG_FILES["policy_rc_d"],
    CONFIG_FILES["postfix_lmtp_header_cleanup"],
    CONFIG_FILES["postfix_login_map"],
    CONFIG_FILES["postfix_main"],
    CONFIG_FILES["postfix_master"],
    CONFIG_FILES["postfix_smtp_tls_policy_map"],
    CONFIG_FILES["postfix_smtp_tls_policy_map_db"],
    CONFIG_FILES["postfix_submission_header_cleanup"],
    CONFIG_FILES["systemd_dovecot_restart"],
    CONFIG_FILES["systemd_mtasts_daemon"],
    CONFIG_FILES["systemd_opendkim_restart"],
    CONFIG_FILES["systemd_postfix_restart"],
    CONFIG_FILES["unbound_chatmail"],
    WEB_PATHS["metrics"],
    WEB_PATHS["newemail_cgi"],
    BINARY_PATHS["chatmail_turn"],
    BINARY_PATHS["filtermail"],
    BINARY_PATHS["iroh_relay"],
    BINARY_PATHS["mtail"],
]

PACKAGE_CONFIG_DIRS = [
    CONFIG_DIRS["dkimkeys"],
    CONFIG_DIRS["dovecot"],
    CONFIG_DIRS["nginx"],
    CONFIG_DIRS["opendkim"],
    CONFIG_DIRS["postfix"],
    CONFIG_DIRS["unbound"],
]

RELAY_DIRS = [
    CONFIG_DIRS["mtail"],
    STATE_DIRS["from_cmdeploy"],
    CHATMAILD_PATHS["base_dir"],
    STATE_DIRS["postfix_mta_sts_resolver"],
    STATE_DIRS["var_lib_dovecot"],
    STATE_DIRS["var_lib_nginx"],
    STATE_DIRS["var_lib_postfix"],
    STATE_DIRS["var_lib_unbound"],
    STATE_DIRS["var_log_nginx"],
    STATE_DIRS["var_spool_postfix"],
    WEB_PATHS["html_dir"],
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
        _remove_file(TLS_PATHS["self_cert"])
        _remove_file(TLS_PATHS["self_key"])
    elif config.tls_cert_mode == "acme":
        _remove_dir(ACME_PATHS["etc_dir"])
        _remove_dir(ACME_PATHS["var_dir"])


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
