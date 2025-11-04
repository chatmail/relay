"""
Chat Mail pyinfra deploy.
"""

import importlib.resources
import io
import shutil
import subprocess
import sys
from io import StringIO
from pathlib import Path

from chatmaild.config import Config, read_config
from cmdeploy.cmdeploy import Out
from pyinfra import facts, host, logger
from pyinfra.api import FactBase
from pyinfra.facts.files import File, Sha256File
from pyinfra.facts.server import Sysctl
from pyinfra.facts.systemd import SystemdEnabled
from pyinfra.operations import apt, files, pip, server, systemd

from .acmetool import AcmetoolDeployer
from .deployer import Deployer
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
        src=importlib.resources.files(__package__).joinpath("metrics.cron.j2"),
        dest="/etc/cron.d/chatmail-metrics",
        user="root",
        group="root",
        mode="644",
        config={
            "mailboxes_dir": config.mailboxes_dir,
            "execpath": f"{remote_venv_dir}/bin/chatmail-metrics",
        },
    )


def _configure_remote_units(mail_domain, units) -> None:
    remote_base_dir = "/usr/local/lib/chatmaild"
    remote_venv_dir = f"{remote_base_dir}/venv"
    remote_chatmail_inipath = f"{remote_base_dir}/chatmail.ini"
    root_owned = dict(user="root", group="root", mode="644")

    # install systemd units
    for fn in units:
        execpath = fn if fn != "filtermail-incoming" else "filtermail"
        params = dict(
            execpath=f"{remote_venv_dir}/bin/{execpath}",
            config_path=remote_chatmail_inipath,
            remote_venv_dir=remote_venv_dir,
            mail_domain=mail_domain,
        )

        basename = fn if "." in fn else f"{fn}.service"

        source_path = importlib.resources.files(__package__).joinpath("service", f"{basename}.f")
        content = source_path.read_text().format(**params).encode()

        files.put(
            name=f"Upload {basename}",
            src=io.BytesIO(content),
            dest=f"/etc/systemd/system/{basename}",
            **root_owned,
        )


def _activate_remote_units(units) -> None:
    # activate systemd units
    for fn in units:
        basename = fn if "." in fn else f"{fn}.service"

        if fn == "chatmail-expire" or fn == "chatmail-fsreport":
            # don't auto-start but let the corresponding timer trigger execution
            enabled = False
        else:
            enabled = True
        systemd.service(
            name=f"Setup {basename}",
            service=basename,
            running=enabled,
            enabled=enabled,
            restarted=enabled,
            daemon_reload=True,
        )



def _configure_opendkim(domain: str, dkim_selector: str = "dkim") -> bool:
    """Configures OpenDKIM"""
    need_restart = False

    main_config = files.template(
        src=importlib.resources.files(__package__).joinpath("opendkim/opendkim.conf"),
        dest="/etc/opendkim.conf",
        user="root",
        group="root",
        mode="644",
        config={"domain_name": domain, "opendkim_selector": dkim_selector},
    )
    need_restart |= main_config.changed

    screen_script = files.put(
        src=importlib.resources.files(__package__).joinpath("opendkim/screen.lua"),
        dest="/etc/opendkim/screen.lua",
        user="root",
        group="root",
        mode="644",
    )
    need_restart |= screen_script.changed

    final_script = files.put(
        src=importlib.resources.files(__package__).joinpath("opendkim/final.lua"),
        dest="/etc/opendkim/final.lua",
        user="root",
        group="root",
        mode="644",
    )
    need_restart |= final_script.changed

    files.directory(
        name="Add opendkim directory to /etc",
        path="/etc/opendkim",
        user="opendkim",
        group="opendkim",
        mode="750",
        present=True,
    )

    keytable = files.template(
        src=importlib.resources.files(__package__).joinpath("opendkim/KeyTable"),
        dest="/etc/dkimkeys/KeyTable",
        user="opendkim",
        group="opendkim",
        mode="644",
        config={"domain_name": domain, "opendkim_selector": dkim_selector},
    )
    need_restart |= keytable.changed

    signing_table = files.template(
        src=importlib.resources.files(__package__).joinpath("opendkim/SigningTable"),
        dest="/etc/dkimkeys/SigningTable",
        user="opendkim",
        group="opendkim",
        mode="644",
        config={"domain_name": domain, "opendkim_selector": dkim_selector},
    )
    need_restart |= signing_table.changed
    files.directory(
        name="Add opendkim socket directory to /var/spool/postfix",
        path="/var/spool/postfix/opendkim",
        user="opendkim",
        group="opendkim",
        mode="750",
        present=True,
    )

    if not host.get_fact(File, f"/etc/dkimkeys/{dkim_selector}.private"):
        server.shell(
            name="Generate OpenDKIM domain keys",
            commands=[
                f"/usr/sbin/opendkim-genkey -D /etc/dkimkeys -d {domain} -s {dkim_selector}"
            ],
            _use_su_login=True,
            _su_user="opendkim",
        )

    service_file = files.put(
        name="Configure opendkim to restart once a day",
        src=importlib.resources.files(__package__).joinpath("opendkim/systemd.conf"),
        dest="/etc/systemd/system/opendkim.service.d/10-prevent-memory-leak.conf",
    )
    need_restart |= service_file.changed

    return need_restart


class OpendkimDeployer(Deployer):
    def __init__(self, *, mail_domain, **kwargs):
        super().__init__(**kwargs)
        self.mail_domain = mail_domain

    @staticmethod
    def required_users():
        return [
            ("opendkim", None, ["opendkim"]),
        ]

    @staticmethod
    def install_impl():
        apt.packages(
            name="apt install opendkim opendkim-tools",
            packages=["opendkim", "opendkim-tools"],
        )

    def configure_impl(self):
        self.need_restart = _configure_opendkim(self.mail_domain, "opendkim")

    def activate_impl(self):
        systemd.service(
            name="Start and enable OpenDKIM",
            service="opendkim.service",
            running=True,
            enabled=True,
            daemon_reload=self.need_restart,
            restarted=self.need_restart,
        )
        self.need_restart = False


class UnboundDeployer(Deployer):
    @staticmethod
    def install_impl():
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
            src=importlib.resources.files(__package__).joinpath("policy-rc.d"),
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

    def configure_impl(self):
        server.shell(
            name="Generate root keys for validating DNSSEC",
            commands=[
                "unbound-anchor -a /var/lib/unbound/root.key || true",
            ],
        )

    def activate_impl(self):
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
    def configure_impl(self):
        # Remove configuration.
        files.file("/etc/mta-sts-daemon.yml", present=False)
        files.directory("/usr/local/lib/postfix-mta-sts-resolver", present=False)
        files.file("/etc/systemd/system/mta-sts-daemon.service", present=False)

    def activate_impl(self):
        systemd.service(
            name="Stop MTA-STS daemon",
            service="mta-sts-daemon.service",
            daemon_reload=True,
            running=False,
            enabled=False,
        )


def _configure_postfix(config: Config, debug: bool = False) -> bool:
    """Configures Postfix SMTP server."""
    need_restart = False

    main_config = files.template(
        src=importlib.resources.files(__package__).joinpath("postfix/main.cf.j2"),
        dest="/etc/postfix/main.cf",
        user="root",
        group="root",
        mode="644",
        config=config,
        disable_ipv6=config.disable_ipv6,
    )
    need_restart |= main_config.changed

    master_config = files.template(
        src=importlib.resources.files(__package__).joinpath("postfix/master.cf.j2"),
        dest="/etc/postfix/master.cf",
        user="root",
        group="root",
        mode="644",
        debug=debug,
        config=config,
    )
    need_restart |= master_config.changed

    header_cleanup = files.put(
        src=importlib.resources.files(__package__).joinpath(
            "postfix/submission_header_cleanup"
        ),
        dest="/etc/postfix/submission_header_cleanup",
        user="root",
        group="root",
        mode="644",
    )
    need_restart |= header_cleanup.changed

    # Login map that 1:1 maps email address to login.
    login_map = files.put(
        src=importlib.resources.files(__package__).joinpath("postfix/login_map"),
        dest="/etc/postfix/login_map",
        user="root",
        group="root",
        mode="644",
    )
    need_restart |= login_map.changed

    return need_restart


class PostfixDeployer(Deployer):
    def __init__(self, *, config, disable_mail, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.disable_mail = disable_mail
        self.was_restarted = False

    @staticmethod
    def required_users():
        return [
            ("postfix", None, ["opendkim"]),
        ]

    @staticmethod
    def install_impl():
        apt.packages(
            name="Install Postfix",
            packages="postfix",
        )

    def configure_impl(self):
        self.need_restart = _configure_postfix(self.config)

    def activate_impl(self):
        restart = False if self.disable_mail else self.need_restart

        systemd.service(
            name="disable postfix for now" if self.disable_mail else "Start and enable Postfix",
            service="postfix.service",
            running=False if self.disable_mail else True,
            enabled=False if self.disable_mail else True,
            restarted=restart,
        )
        self.was_restarted = restart
        self.need_restart = False


def _install_dovecot_package(package: str, arch: str):
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

    apt.deb(name=f"Install dovecot-{package}", src=deb_filename)


def _configure_dovecot(config: Config, debug: bool = False) -> bool:
    """Configures Dovecot IMAP server."""
    need_restart = False

    main_config = files.template(
        src=importlib.resources.files(__package__).joinpath("dovecot/dovecot.conf.j2"),
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
        src=importlib.resources.files(__package__).joinpath("dovecot/auth.conf"),
        dest="/etc/dovecot/auth.conf",
        user="root",
        group="root",
        mode="644",
    )
    need_restart |= auth_config.changed
    lua_push_notification_script = files.put(
        src=importlib.resources.files(__package__).joinpath(
            "dovecot/push_notification.lua"
        ),
        dest="/etc/dovecot/push_notification.lua",
        user="root",
        group="root",
        mode="644",
    )
    need_restart |= lua_push_notification_script.changed

    # remove historic expunge script
    # which is now implemented through a systemd chatmail-expire service/timer
    files.file(
        path="/etc/cron.d/expunge",
        present=False,
    )

    # as per https://doc.dovecot.org/configuration_manual/os/
    # it is recommended to set the following inotify limits
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

    return need_restart


class DovecotDeployer(Deployer):
    def __init__(self, *, config, disable_mail, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.disable_mail = disable_mail
        self.was_restarted = False

    @staticmethod
    def install_impl():
        arch = host.get_fact(facts.server.Arch)
        if not "dovecot.service" in host.get_fact(SystemdEnabled):
            _install_dovecot_package("core", arch)
            _install_dovecot_package("imapd", arch)
            _install_dovecot_package("lmtpd", arch)

    def configure_impl(self):
        self.need_restart = _configure_dovecot(self.config)

    def activate_impl(self):
        restart = False if self.disable_mail else self.need_restart

        systemd.service(
            name="disable dovecot for now" if self.disable_mail else "Start and enable Dovecot",
            service="dovecot.service",
            running=False if self.disable_mail else True,
            enabled=False if self.disable_mail else True,
            restarted=restart,
        )
        self.was_restarted = restart
        self.need_restart = False


def _configure_nginx(config: Config, debug: bool = False) -> bool:
    """Configures nginx HTTP server."""
    need_restart = False

    main_config = files.template(
        src=importlib.resources.files(__package__).joinpath("nginx/nginx.conf.j2"),
        dest="/etc/nginx/nginx.conf",
        user="root",
        group="root",
        mode="644",
        config={"domain_name": config.mail_domain},
        disable_ipv6=config.disable_ipv6,
    )
    need_restart |= main_config.changed

    autoconfig = files.template(
        src=importlib.resources.files(__package__).joinpath("nginx/autoconfig.xml.j2"),
        dest="/var/www/html/.well-known/autoconfig/mail/config-v1.1.xml",
        user="root",
        group="root",
        mode="644",
        config={"domain_name": config.mail_domain},
    )
    need_restart |= autoconfig.changed

    mta_sts_config = files.template(
        src=importlib.resources.files(__package__).joinpath("nginx/mta-sts.txt.j2"),
        dest="/var/www/html/.well-known/mta-sts.txt",
        user="root",
        group="root",
        mode="644",
        config={"domain_name": config.mail_domain},
    )
    need_restart |= mta_sts_config.changed

    # install CGI newemail script
    #
    cgi_dir = "/usr/lib/cgi-bin"
    files.directory(
        name=f"Ensure {cgi_dir} exists",
        path=cgi_dir,
        user="root",
        group="root",
    )

    files.put(
        name="Upload cgi newemail.py script",
        src=importlib.resources.files("chatmaild").joinpath("newemail.py").open("rb"),
        dest=f"{cgi_dir}/newemail.py",
        user="root",
        group="root",
        mode="755",
    )

    return need_restart


class NginxDeployer(Deployer):
    def __init__(self, *, config, **kwargs):
        super().__init__(**kwargs)
        self.config = config

    @staticmethod
    def install_impl():
        #
        # If we allow nginx to start up on install, it will grab port
        # 80, which then will block acmetool from listening on the port.
        # That in turn prevents getting certificates, which then causes
        # an error when we try to start nginx on the custom config
        # that leaves port 80 open but also requires certificates to
        # be present.  To avoid getting into that interlocking mess,
        # we use policy-rc.d to prevent nginx from starting up when it
        # is installed.
        #
        # This approach allows us to avoid performing any explicit
        # systemd operations during the install stage (as opposed to
        # allowing it to start and then forcing it to stop), which allows
        # the install stage to run in non-systemd environments like a
        # container image build.
        #
        # For documentation about policy-rc.d, see:
        # https://people.debian.org/~hmh/invokerc.d-policyrc.d-specification.txt
        #
        files.put(
            src=importlib.resources.files(__package__).joinpath("policy-rc.d"),
            dest="/usr/sbin/policy-rc.d",
            user="root",
            group="root",
            mode="755",
        )

        apt.packages(
            name="Install nginx",
            packages=["nginx", "libnginx-mod-stream"],
        )

        files.file("/usr/sbin/policy-rc.d", present=False)

    def configure_impl(self):
        self.need_restart = _configure_nginx(self.config)

    def activate_impl(self):
        systemd.service(
            name="Start and enable nginx",
            service="nginx.service",
            running=True,
            enabled=True,
            restarted=self.need_restart,
        )
        self.need_restart = False


class WebsiteDeployer(Deployer):
    def __init__(self, *, config, **kwargs):
        super().__init__(**kwargs)
        self.config = config

    @staticmethod
    def install_impl():
        files.directory(
            name="Ensure /var/www exists",
            path="/var/www",
            user="root",
            group="root",
            mode="755",
            present=True,
        )

    def configure_impl(self):
        www_path, src_dir, build_dir = get_paths(self.config)
        # if www_folder was set to a non-existing folder, skip upload
        if not www_path.is_dir():
            logger.warning("Building web pages is disabled in chatmail.ini, skipping")
        elif (path := find_merge_conflict(src_dir)) is not None:
            logger.warning(f"Merge conflict found in {path}, skipping website deployment. Fix merge conflict if you want to upload your web page.")
        else:
            # if www_folder is a hugo page, build it
            if build_dir:
                www_path = build_webpages(src_dir, build_dir, self.config)
            # if it is not a hugo page, upload it as is
            files.rsync(
                f"{www_path}/", "/var/www/html", flags=["-avz", "--chown=www-data"]
            )


class RspamdDeployer(Deployer):
    @staticmethod
    def install_impl():
        apt.packages(name="Remove rspamd", packages="rspamd", present=False)


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
    def __init__(self, *, mail_domain, **kwargs):
        super().__init__(**kwargs)
        self.mail_domain = mail_domain
        self.daemon_reload = False

    @staticmethod
    def install_impl():
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

            #
            # This will set need_restart when called from an object's
            # install() method.
            #
            return True

    def configure_impl(self):
        source_path = importlib.resources.files(__package__).joinpath(
            "service", "turnserver.service.f"
        )
        content = source_path.read_text().format(mail_domain=self.mail_domain).encode()

        systemd_unit = files.put(
            name="Upload turnserver.service",
            src=io.BytesIO(content),
            dest="/etc/systemd/system/turnserver.service",
            user="root",
            group="root",
            mode="644",
        )
        self.daemon_reload = systemd_unit.changed
        self.need_restart |= systemd_unit.changed

    def activate_impl(self):
        systemd.service(
            name="Setup turnserver service",
            service="turnserver.service",
            running=True,
            enabled=True,
            restarted=self.need_restart,
            daemon_reload=self.daemon_reload,
        )
        self.daemon_reload = False
        self.need_restart = False


class MtailDeployer(Deployer):
    def __init__(self, *, mtail_address, **kwargs):
        super().__init__(**kwargs)
        self.mtail_address = mtail_address

    @staticmethod
    def install_impl():
        # Uninstall mtail package, we are going to install a static binary.
        apt.packages(name="Uninstall mtail", packages=["mtail"], present=False)

        (url, sha256sum) = {
            "x86_64": (
                "https://github.com/google/mtail/releases/download/v3.0.8/mtail_3.0.8_linux_amd64.tar.gz",
                "123c2ee5f48c3eff12ebccee38befd2233d715da736000ccde49e3d5607724e4",
            ),
            "aarch64": (
                "https://github.com/google/mtail/releases/download/v3.0.8/mtail_3.0.8_linux_arm64.tar.gz",
                "aa04811c0929b6754408676de520e050c45dddeb3401881888a092c9aea89cae",
            ),
        }[host.get_fact(facts.server.Arch)]

        server.shell(
            name="Download mtail",
            commands=[
                f"(echo '{sha256sum} /usr/local/bin/mtail' | sha256sum -c) || (curl -L {url} | gunzip | tar -x -f - mtail -O >/usr/local/bin/mtail.new && mv /usr/local/bin/mtail.new /usr/local/bin/mtail)",
                "chmod 755 /usr/local/bin/mtail",
            ],
        )

    def configure_impl(self):
        # Using our own systemd unit instead of `/usr/lib/systemd/system/mtail.service`.
        # This allows to read from journalctl instead of log files.
        files.template(
            src=importlib.resources.files(__package__).joinpath(
                "mtail/mtail.service.j2"
            ),
            dest="/etc/systemd/system/mtail.service",
            user="root",
            group="root",
            mode="644",
            address=self.mtail_address or "127.0.0.1",
            port=3903,
        )

        mtail_conf = files.put(
            name="Mtail configuration",
            src=importlib.resources.files(__package__).joinpath(
                "mtail/delivered_mail.mtail"
            ),
            dest="/etc/mtail/delivered_mail.mtail",
            user="root",
            group="root",
            mode="644",
        )
        self.need_restart = mtail_conf.changed

    def activate_impl(self):
        systemd.service(
            name="Start and enable mtail",
            service="mtail.service",
            running=bool(self.mtail_address),
            enabled=bool(self.mtail_address),
            restarted=self.need_restart,
        )
        self.need_restart = False


class IrohDeployer(Deployer):
    def __init__(self, *, enable_iroh_relay, **kwargs):
        super().__init__(**kwargs)
        self.enable_iroh_relay = enable_iroh_relay

    @staticmethod
    def install_impl():
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

            #
            # This will set need_restart when called from an object's
            # install() method.
            #
            return True

    def configure_impl(self):
        systemd_unit = files.put(
            name="Upload iroh-relay systemd unit",
            src=importlib.resources.files(__package__).joinpath("iroh-relay.service"),
            dest="/etc/systemd/system/iroh-relay.service",
            user="root",
            group="root",
            mode="644",
        )
        self.need_restart |= systemd_unit.changed

        iroh_config = files.put(
            name="Upload iroh-relay config",
            src=importlib.resources.files(__package__).joinpath("iroh-relay.toml"),
            dest="/etc/iroh-relay.toml",
            user="root",
            group="root",
            mode="644",
        )
        self.need_restart |= iroh_config.changed

    def activate_impl(self):
        systemd.service(
            name="Start and enable iroh-relay",
            service="iroh-relay.service",
            running=True,
            enabled=self.enable_iroh_relay,
            restarted=self.need_restart,
        )
        self.need_restart = False


class JournaldDeployer(Deployer):
    def configure_impl(self):
        journald_conf = files.put(
            name="Configure journald",
            src=importlib.resources.files(__package__).joinpath("journald.conf"),
            dest="/etc/systemd/journald.conf",
            user="root",
            group="root",
            mode="644",
        )
        self.need_restart = journald_conf.changed

    def activate_impl(self):
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
    def __init__(self, *, dovecot_deployer, postfix_deployer, **kwargs):
        super().__init__(**kwargs)
        self.dovecot_deployer = dovecot_deployer
        self.postfix_deployer = postfix_deployer

    @staticmethod
    def install_impl():
        apt.packages(
            # required for setfacl for echobot
            name="Install acl",
            packages="acl",
        )

    def activate_impl(self):
        systemd.service(
            name="Restart echobot if postfix and dovecot were just started",
            service="echobot.service",
            restarted=self.postfix_deployer.was_restarted and self.dovecot_deployer.was_restarted,
        )


class ChatmailVenvDeployer(Deployer):
    def __init__(self, *, config, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.units = (
            "doveauth",
            "filtermail",
            "filtermail-incoming",
            "echobot",
            "chatmail-metadata",
            "lastlogin",
            "turnserver",
            "chatmail-expire",
            "chatmail-expire.timer",
            "chatmail-fsreport",
            "chatmail-fsreport.timer",
        )

    @staticmethod
    def install_impl():
        _install_remote_venv_with_chatmaild()

    def configure_impl(self):
        _configure_remote_venv_with_chatmaild(self.config)
        _configure_remote_units(self.config.mail_domain, self.units)

    def activate_impl(self):
        _activate_remote_units(self.units)


class ChatmailDeployer(Deployer):
    def __init__(self, *, mail_domain, **kwargs):
        super().__init__(**kwargs)
        self.mail_domain = mail_domain

    @staticmethod
    def required_users():
        return [
            ("vmail", "vmail", None),
            ("echobot", None, None),
            ("iroh", None, None),
        ]

    @staticmethod
    def install_impl():
        # Remove OBS repository key that is no longer used.
        files.file("/etc/apt/keyrings/obs-home-deltachat.gpg", present=False)

        files.line(
            name="Remove DeltaChat OBS home repository from sources.list",
            path="/etc/apt/sources.list",
            line="deb [signed-by=/etc/apt/keyrings/obs-home-deltachat.gpg] https://download.opensuse.org/repositories/home:/deltachat/Debian_12/ ./",
            escape_regex_characters=True,
            present=False,
        )

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

    def configure_impl(self):
        # This file is used by auth proxy.
        # https://wiki.debian.org/EtcMailName
        server.shell(
            name="Setup /etc/mailname",
            commands=[
                f"echo {self.mail_domain} >/etc/mailname; chmod 644 /etc/mailname"
            ],
        )


class FcgiwrapDeployer(Deployer):
    @staticmethod
    def install_impl():
        apt.packages(
            name="Install fcgiwrap",
            packages=["fcgiwrap"],
        )

    def activate_impl(self):
        systemd.service(
            name="Start and enable fcgiwrap",
            service="fcgiwrap.service",
            running=True,
            enabled=True,
        )


def deploy_chatmail(config_path: Path, disable_mail: bool) -> None:
    """Deploy a chat-mail instance.

    :param config_path: path to chatmail.ini
    :param disable_mail: whether to disable postfix & dovecot
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

    chatmail_deployer = ChatmailDeployer(mail_domain=mail_domain)
    journald_deployer = JournaldDeployer()
    unbound_deployer = UnboundDeployer()
    turn_deployer = TurnDeployer(mail_domain=mail_domain)
    iroh_deployer = IrohDeployer(enable_iroh_relay=config.enable_iroh_relay)

    # Deploy acmetool to have TLS certificates.
    acmetool_deployer = AcmetoolDeployer(email=config.acme_email, domains=tls_domains)

    website_deployer = WebsiteDeployer(config=config)
    chatmail_venv_deployer = ChatmailVenvDeployer(config=config)
    mtasts_deployer = MtastsDeployer()
    opendkim_deployer = OpendkimDeployer(mail_domain=mail_domain)

    # Dovecot should be started before Postfix
    # because it creates authentication socket
    # required by Postfix.
    dovecot_deployer = DovecotDeployer(config=config, disable_mail=disable_mail)
    postfix_deployer = PostfixDeployer(config=config, disable_mail=disable_mail)

    fcgiwrap_deployer = FcgiwrapDeployer()
    nginx_deployer = NginxDeployer(config=config)
    rspamd_deployer = RspamdDeployer()
    echobot_deployer = EchobotDeployer(
        dovecot_deployer=dovecot_deployer, postfix_deployer=postfix_deployer
    )
    mtail_deployer = MtailDeployer(mtail_address=config.mtail_address)

    all_deployers = [
        chatmail_deployer,
        journald_deployer,
        unbound_deployer,
        turn_deployer,
        iroh_deployer,
        acmetool_deployer,
        website_deployer,
        chatmail_venv_deployer,
        mtasts_deployer,
        opendkim_deployer,
        dovecot_deployer,
        postfix_deployer,
        fcgiwrap_deployer,
        nginx_deployer,
        rspamd_deployer,
        echobot_deployer,
        mtail_deployer,
    ]

    #
    # Create all groups before users, because some users reference groups
    # from other classes.
    #
    for deployer in all_deployers:
        deployer.create_groups()

    for deployer in all_deployers:
        deployer.create_users()

    for deployer in all_deployers:
        deployer.install()

    for deployer in all_deployers:
        deployer.configure()

    for deployer in all_deployers:
        deployer.activate()

    files.directory(
        name="Ensure old logs on disk are deleted",
        path="/var/log/journal/",
        present=False,
    )

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
