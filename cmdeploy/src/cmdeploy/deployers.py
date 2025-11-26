"""
Chat Mail pyinfra deploy.
"""

import shutil
import subprocess
import sys
from io import StringIO
from pathlib import Path

from chatmaild.config import read_config
from pyinfra import facts, host, logger
from pyinfra.api import FactBase
from pyinfra.facts.files import Sha256File
from pyinfra.facts.systemd import SystemdEnabled
from pyinfra.operations import apt, files, pip, server, systemd

from cmdeploy.cmdeploy import Out

from .acmetool import AcmetoolDeployer
from .basedeploy import (
    Deployer,
    Deployment,
    activate_remote_units,
    configure_remote_units,
    get_resource,
)
from .dovecot.deployer import DovecotDeployer
from .mtail.deployer import MtailDeployer
from .nginx.deployer import NginxDeployer
from .opendkim.deployer import OpendkimDeployer
from .postfix.deployer import PostfixDeployer
from .www import build_webpages, find_merge_conflict, get_paths


class Port(FactBase):
    """
    Returns the process occuping a port.
    """

    def command(self, port: int) -> str:
        return (
            "ss -lptn 'src :%d' | awk 'NR>1 {print $6,$7}' | sed 's/users:((\"//;s/\".*//'"
            % (port,)
        )

    def process(self, output: [str]) -> str:
        return output[0]


def _build_chatmaild(dist_dir) -> None:
    dist_dir = Path(dist_dir).resolve()
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir()
    subprocess.check_output(
        [sys.executable, "-m", "build", "-n"]
        + ["--sdist", "chatmaild", "--outdir", str(dist_dir)]
    )
    entries = list(dist_dir.iterdir())
    assert len(entries) == 1
    return entries[0]


def remove_legacy_artifacts():
    # disable legacy doveauth-dictproxy.service
    if host.get_fact(SystemdEnabled).get("doveauth-dictproxy.service"):
        systemd.service(
            name="Disable legacy doveauth-dictproxy.service",
            service="doveauth-dictproxy.service",
            running=False,
            enabled=False,
        )


def _install_remote_venv_with_chatmaild() -> None:
    remove_legacy_artifacts()
    dist_file = _build_chatmaild(dist_dir=Path("chatmaild/dist"))
    remote_base_dir = "/usr/local/lib/chatmaild"
    remote_dist_file = f"{remote_base_dir}/dist/{dist_file.name}"
    remote_venv_dir = f"{remote_base_dir}/venv"
    root_owned = dict(user="root", group="root", mode="644")

    apt.packages(
        name="apt install python3-virtualenv",
        packages=["python3-virtualenv"],
    )

    files.put(
        name="Upload chatmaild source package",
        src=dist_file.open("rb"),
        dest=remote_dist_file,
        create_remote_dir=True,
        **root_owned,
    )

    pip.virtualenv(
        name=f"chatmaild virtualenv {remote_venv_dir}",
        path=remote_venv_dir,
        always_copy=True,
    )

    apt.packages(
        name="install gcc and headers to build crypt_r source package",
        packages=["gcc", "python3-dev"],
    )

    server.shell(
        name=f"forced pip-install {dist_file.name}",
        commands=[
            f"{remote_venv_dir}/bin/pip install --force-reinstall {remote_dist_file}"
        ],
    )


def _configure_remote_venv_with_chatmaild(config) -> None:
    remote_base_dir = "/usr/local/lib/chatmaild"
    remote_venv_dir = f"{remote_base_dir}/venv"
    remote_chatmail_inipath = f"{remote_base_dir}/chatmail.ini"
    root_owned = dict(user="root", group="root", mode="644")

    files.put(
        name=f"Upload {remote_chatmail_inipath}",
        src=config._getbytefile(),
        dest=remote_chatmail_inipath,
        **root_owned,
    )

    files.template(
        src=get_resource("metrics.cron.j2"),
        dest="/etc/cron.d/chatmail-metrics",
        user="root",
        group="root",
        mode="644",
        config={
            "mailboxes_dir": config.mailboxes_dir,
            "execpath": f"{remote_venv_dir}/bin/chatmail-metrics",
        },
    )


class UnboundDeployer(Deployer):
    def install(self):
        # Run local DNS resolver `unbound`.
        # `resolvconf` takes care of setting up /etc/resolv.conf
        # to use 127.0.0.1 as the resolver.

        #
        # On an IPv4-only system, if unbound is started but not
        # configured, it causes subsequent steps to fail to resolve hosts.
        # Here, we use policy-rc.d to prevent unbound from starting up
        # on initial install.  Later, we will configure it and start it.
        #
        # For documentation about policy-rc.d, see:
        # https://people.debian.org/~hmh/invokerc.d-policyrc.d-specification.txt
        #
        files.put(
            src=get_resource("policy-rc.d"),
            dest="/usr/sbin/policy-rc.d",
            user="root",
            group="root",
            mode="755",
        )

        apt.packages(
            name="Install unbound",
            packages=["unbound", "unbound-anchor", "dnsutils"],
        )

        files.file("/usr/sbin/policy-rc.d", present=False)

    def configure(self):
        server.shell(
            name="Generate root keys for validating DNSSEC",
            commands=[
                "unbound-anchor -a /var/lib/unbound/root.key || true",
            ],
        )

    def activate(self):
        server.shell(
            name="Generate root keys for validating DNSSEC",
            commands=[
                "systemctl reset-failed unbound.service",
            ],
        )

        systemd.service(
            name="Start and enable unbound",
            service="unbound.service",
            running=True,
            enabled=True,
        )


class MtastsDeployer(Deployer):
    def configure(self):
        # Remove configuration.
        files.file("/etc/mta-sts-daemon.yml", present=False)
        files.directory("/usr/local/lib/postfix-mta-sts-resolver", present=False)
        files.file("/etc/systemd/system/mta-sts-daemon.service", present=False)

    def activate(self):
        systemd.service(
            name="Stop MTA-STS daemon",
            service="mta-sts-daemon.service",
            daemon_reload=True,
            running=False,
            enabled=False,
        )


class WebsiteDeployer(Deployer):
    def __init__(self, config):
        self.config = config

    def install(self):
        files.directory(
            name="Ensure /var/www exists",
            path="/var/www",
            user="root",
            group="root",
            mode="755",
            present=True,
        )

    def configure(self):
        www_path, src_dir, build_dir = get_paths(self.config)
        # if www_folder was set to a non-existing folder, skip upload
        if not www_path.is_dir():
            logger.warning("Building web pages is disabled in chatmail.ini, skipping")
        elif (path := find_merge_conflict(src_dir)) is not None:
            logger.warning(
                f"Merge conflict found in {path}, skipping website deployment. Fix merge conflict if you want to upload your web page."
            )
        else:
            # if www_folder is a hugo page, build it
            if build_dir:
                www_path = build_webpages(src_dir, build_dir, self.config)
            # if it is not a hugo page, upload it as is
            files.rsync(
                f"{www_path}/", "/var/www/html", flags=["-avz", "--chown=www-data"]
            )


class LegacyRemoveDeployer(Deployer):
    def install(self):
        apt.packages(name="Remove rspamd", packages="rspamd", present=False)

        # remove historic expunge script
        # which is now implemented through a systemd timer (chatmail-expire)
        files.file(
            path="/etc/cron.d/expunge",
            present=False,
        )

        # Remove OBS repository key that is no longer used.
        files.file("/etc/apt/keyrings/obs-home-deltachat.gpg", present=False)
        files.line(
            name="Remove DeltaChat OBS home repository from sources.list",
            path="/etc/apt/sources.list",
            line="deb [signed-by=/etc/apt/keyrings/obs-home-deltachat.gpg] https://download.opensuse.org/repositories/home:/deltachat/Debian_12/ ./",
            escape_regex_characters=True,
            present=False,
        )

        # prior relay versions used filelogging
        files.directory(
            name="Ensure old logs on disk are deleted",
            path="/var/log/journal/",
            present=False,
        )


def check_config(config):
    mail_domain = config.mail_domain
    if mail_domain != "testrun.org" and not mail_domain.endswith(".testrun.org"):
        blocked_words = "merlinux schmieder testrun.org".split()
        for key in config.__dict__:
            value = config.__dict__[key]
            if key.startswith("privacy") and any(
                x in str(value) for x in blocked_words
            ):
                raise ValueError(
                    f"please set your own privacy contacts/addresses in {config._inipath}"
                )
    return config


class TurnDeployer(Deployer):
    def __init__(self, mail_domain):
        self.mail_domain = mail_domain
        self.units = ["turnserver"]

    def install(self):
        (url, sha256sum) = {
            "x86_64": (
                "https://github.com/chatmail/chatmail-turn/releases/download/v0.3/chatmail-turn-x86_64-linux",
                "841e527c15fdc2940b0469e206188ea8f0af48533be12ecb8098520f813d41e4",
            ),
            "aarch64": (
                "https://github.com/chatmail/chatmail-turn/releases/download/v0.3/chatmail-turn-aarch64-linux",
                "a5fc2d06d937b56a34e098d2cd72a82d3e89967518d159bf246dc69b65e81b42",
            ),
        }[host.get_fact(facts.server.Arch)]

        existing_sha256sum = host.get_fact(Sha256File, "/usr/local/bin/chatmail-turn")
        if existing_sha256sum != sha256sum:
            server.shell(
                name="Download chatmail-turn",
                commands=[
                    f"(curl -L {url} >/usr/local/bin/chatmail-turn.new && (echo '{sha256sum} /usr/local/bin/chatmail-turn.new' | sha256sum -c) && mv /usr/local/bin/chatmail-turn.new /usr/local/bin/chatmail-turn)",
                    "chmod 755 /usr/local/bin/chatmail-turn",
                ],
            )

    def configure(self):
        configure_remote_units(self.mail_domain, self.units)

    def activate(self):
        activate_remote_units(self.units)


class IrohDeployer(Deployer):
    def __init__(self, enable_iroh_relay):
        self.enable_iroh_relay = enable_iroh_relay

    def install(self):
        (url, sha256sum) = {
            "x86_64": (
                "https://github.com/n0-computer/iroh/releases/download/v0.35.0/iroh-relay-v0.35.0-x86_64-unknown-linux-musl.tar.gz",
                "45c81199dbd70f8c4c30fef7f3b9727ca6e3cea8f2831333eeaf8aa71bf0fac1",
            ),
            "aarch64": (
                "https://github.com/n0-computer/iroh/releases/download/v0.35.0/iroh-relay-v0.35.0-aarch64-unknown-linux-musl.tar.gz",
                "f8ef27631fac213b3ef668d02acd5b3e215292746a3fc71d90c63115446008b1",
            ),
        }[host.get_fact(facts.server.Arch)]

        existing_sha256sum = host.get_fact(Sha256File, "/usr/local/bin/iroh-relay")
        if existing_sha256sum != sha256sum:
            server.shell(
                name="Download iroh-relay",
                commands=[
                    f"(curl -L {url} | gunzip | tar -x -f - ./iroh-relay -O >/usr/local/bin/iroh-relay.new && (echo '{sha256sum} /usr/local/bin/iroh-relay.new' | sha256sum -c) && mv /usr/local/bin/iroh-relay.new /usr/local/bin/iroh-relay)",
                    "chmod 755 /usr/local/bin/iroh-relay",
                ],
            )

            self.need_restart = True

    def configure(self):
        systemd_unit = files.put(
            name="Upload iroh-relay systemd unit",
            src=get_resource("iroh-relay.service"),
            dest="/etc/systemd/system/iroh-relay.service",
            user="root",
            group="root",
            mode="644",
        )
        self.need_restart |= systemd_unit.changed

        iroh_config = files.put(
            name="Upload iroh-relay config",
            src=get_resource("iroh-relay.toml"),
            dest="/etc/iroh-relay.toml",
            user="root",
            group="root",
            mode="644",
        )
        self.need_restart |= iroh_config.changed

    def activate(self):
        systemd.service(
            name="Start and enable iroh-relay",
            service="iroh-relay.service",
            running=True,
            enabled=self.enable_iroh_relay,
            restarted=self.need_restart,
        )
        self.need_restart = False


class JournaldDeployer(Deployer):
    def configure(self):
        journald_conf = files.put(
            name="Configure journald",
            src=get_resource("journald.conf"),
            dest="/etc/systemd/journald.conf",
            user="root",
            group="root",
            mode="644",
        )
        self.need_restart = journald_conf.changed

    def activate(self):
        systemd.service(
            name="Start and enable journald",
            service="systemd-journald.service",
            running=True,
            enabled=True,
            restarted=self.need_restart,
        )
        self.need_restart = False


class EchobotDeployer(Deployer):
    #
    # This deployer depends on the dovecot and postfix deployers because
    # it needs to base its decision of whether to restart the service on
    # whether those two services were restarted.
    #
    def __init__(self, mail_domain):
        self.mail_domain = mail_domain
        self.units = ["echobot"]

    def install(self):
        apt.packages(
            # required for setfacl for echobot
            name="Install acl",
            packages="acl",
        )

    def configure(self):
        configure_remote_units(self.mail_domain, self.units)

    def activate(self):
        activate_remote_units(self.units)


class ChatmailVenvDeployer(Deployer):
    def __init__(self, config):
        self.config = config
        self.units = (
            "filtermail",
            "filtermail-incoming",
            "chatmail-metadata",
            "lastlogin",
            "chatmail-expire",
            "chatmail-expire.timer",
            "chatmail-fsreport",
            "chatmail-fsreport.timer",
        )

    def install(self):
        _install_remote_venv_with_chatmaild()

    def configure(self):
        _configure_remote_venv_with_chatmaild(self.config)
        configure_remote_units(self.config.mail_domain, self.units)

    def activate(self):
        activate_remote_units(self.units)


class ChatmailDeployer(Deployer):
    required_users = [
        ("vmail", "vmail", None),
        ("echobot", None, None),
        ("iroh", None, None),
    ]

    def __init__(self, mail_domain):
        self.mail_domain = mail_domain

    def install(self):
        apt.update(name="apt update", cache_time=24 * 3600)
        apt.upgrade(name="upgrade apt packages", auto_remove=True)

        apt.packages(
            name="Install curl",
            packages=["curl"],
        )

        apt.packages(
            name="Install rsync",
            packages=["rsync"],
        )
        apt.packages(
            name="Ensure cron is installed",
            packages=["cron"],
        )

    def configure(self):
        # This file is used by auth proxy.
        # https://wiki.debian.org/EtcMailName
        server.shell(
            name="Setup /etc/mailname",
            commands=[
                f"echo {self.mail_domain} >/etc/mailname; chmod 644 /etc/mailname"
            ],
        )


class FcgiwrapDeployer(Deployer):
    def install(self):
        apt.packages(
            name="Install fcgiwrap",
            packages=["fcgiwrap"],
        )

    def activate(self):
        systemd.service(
            name="Start and enable fcgiwrap",
            service="fcgiwrap.service",
            running=True,
            enabled=True,
        )


class GithashDeployer(Deployer):
    def activate(self):
        try:
            git_hash = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode()
        except Exception:
            git_hash = "unknown\n"
        try:
            git_diff = subprocess.check_output(["git", "diff"]).decode()
        except Exception:
            git_diff = ""
        files.put(
            name="Upload chatmail relay git commiit hash",
            src=StringIO(git_hash + git_diff),
            dest="/etc/chatmail-version",
            mode="700",
        )


def deploy_chatmail(config_path: Path, disable_mail: bool, docker: bool) -> None:
    """Deploy a chat-mail instance.

    :param config_path: path to chatmail.ini
    :param disable_mail: whether to disable postfix & dovecot
    :param docker: whether it is running in a docker container
    """
    config = read_config(config_path)
    check_config(config)
    mail_domain = config.mail_domain

    if host.get_fact(Port, port=53) != "unbound":
        files.line(
            name="Add 9.9.9.9 to resolv.conf",
            path="/etc/resolv.conf",
            line="nameserver 9.9.9.9",
        )

    if not docker:
        port_services = [
            (["master", "smtpd"], 25),
            ("unbound", 53),
            ("acmetool", 80),
            (["imap-login", "dovecot"], 143),
            ("nginx", 443),
            (["master", "smtpd"], 465),
            (["master", "smtpd"], 587),
            (["imap-login", "dovecot"], 993),
            ("iroh-relay", 3340),
            ("nginx", 8443),
            (["master", "smtpd"], config.postfix_reinject_port),
            (["master", "smtpd"], config.postfix_reinject_port_incoming),
            ("filtermail", config.filtermail_smtp_port),
            ("filtermail", config.filtermail_smtp_port_incoming),
        ]
        for service, port in port_services:
            print(f"Checking if port {port} is available for {service}...")
            running_service = host.get_fact(Port, port=port)
            if running_service:
                if running_service not in service:
                    Out().red(
                        f"Deploy failed: port {port} is occupied by: {running_service}"
                    )
                    exit(1)

    tls_domains = [mail_domain, f"mta-sts.{mail_domain}", f"www.{mail_domain}"]

    all_deployers = [
        ChatmailDeployer(mail_domain),
        LegacyRemoveDeployer(),
        JournaldDeployer(),
        UnboundDeployer(),
        TurnDeployer(mail_domain),
        IrohDeployer(config.enable_iroh_relay),
        AcmetoolDeployer(config.acme_email, tls_domains),
        WebsiteDeployer(config),
        ChatmailVenvDeployer(config),
        MtastsDeployer(),
        OpendkimDeployer(mail_domain),
        # Dovecot should be started before Postfix
        # because it creates authentication socket
        # required by Postfix.
        DovecotDeployer(config, disable_mail),
        PostfixDeployer(config, disable_mail),
        FcgiwrapDeployer(),
        NginxDeployer(config),
        EchobotDeployer(mail_domain),
        MtailDeployer(config.mtail_address),
        GithashDeployer(),
    ]

    Deployment().perform_stages(all_deployers)
