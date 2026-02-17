import os
from pathlib import Path

import iniconfig

from chatmaild.user import User


def read_config(inipath):
    assert Path(inipath).exists(), inipath
    cfg = iniconfig.IniConfig(inipath)
    return Config(inipath, params=cfg.sections["params"])


class Config:
    def __init__(self, inipath, params):
        self._inipath = inipath
        self.mail_domain = params["mail_domain"]
        self.max_user_send_per_minute = int(params.get("max_user_send_per_minute", 60))
        self.max_user_send_burst_size = int(params.get("max_user_send_burst_size", 10))
        self.max_mailbox_size = params.get("max_mailbox_size", "500M")
        self.max_message_size = int(params.get("max_message_size", 31457280))
        self.delete_mails_after = params.get("delete_mails_after", "20")
        self.delete_large_after = params.get("delete_large_after", "7")
        self.delete_inactive_users_after = int(
            params.get("delete_inactive_users_after", 100)
        )
        self.username_min_length = int(params.get("username_min_length", 9))
        self.username_max_length = int(params.get("username_max_length", 9))
        self.password_min_length = int(params.get("password_min_length", 9))
        self.passthrough_senders = params.get("passthrough_senders", "").split()
        self.passthrough_recipients = params.get("passthrough_recipients", "").split()
        self.www_folder = params.get("www_folder", "")
        self.filtermail_smtp_port = int(params.get("filtermail_smtp_port", "10080"))
        self.filtermail_smtp_port_incoming = int(
            params.get("filtermail_smtp_port_incoming", "10081")
        )
        self.postfix_reinject_port = int(params.get("postfix_reinject_port", "10025"))
        self.postfix_reinject_port_incoming = int(
            params.get("postfix_reinject_port_incoming", "10026")
        )
        self.mtail_address = params.get("mtail_address")
        self.disable_ipv6 = params.get("disable_ipv6", "false").lower() == "true"
        self.addr_v4 = os.environ.get("CHATMAIL_ADDR_V4", "")
        self.addr_v6 = os.environ.get("CHATMAIL_ADDR_V6", "")
        self.acme_email = params.get("acme_email", "")
        self.imap_rawlog = params.get("imap_rawlog", "false").lower() == "true"
        self.imap_compress = params.get("imap_compress", "false").lower() == "true"
        if "iroh_relay" not in params:
            self.iroh_relay = "https://" + params["mail_domain"]
            self.enable_iroh_relay = True
        else:
            self.iroh_relay = params["iroh_relay"].strip()
            self.enable_iroh_relay = False
        self.privacy_postal = params.get("privacy_postal")
        self.privacy_mail = params.get("privacy_mail")
        self.privacy_pdo = params.get("privacy_pdo")
        self.privacy_supervisor = params.get("privacy_supervisor")

        # TLS certificate management: derived from the domain name.
        # Domains starting with "_" use self-signed certificates
        # All other domains use ACME.
        if self.mail_domain.startswith("_"):
            self.tls_cert_mode = "self"
            self.tls_cert_path = "/etc/ssl/certs/mailserver.pem"
            self.tls_key_path = "/etc/ssl/private/mailserver.key"
        else:
            self.tls_cert_mode = "acme"
            self.tls_cert_path = f"/var/lib/acme/live/{self.mail_domain}/fullchain"
            self.tls_key_path = f"/var/lib/acme/live/{self.mail_domain}/privkey"

        # deprecated option
        mbdir = params.get("mailboxes_dir", f"/home/vmail/mail/{self.mail_domain}")
        self.mailboxes_dir = Path(mbdir.strip())

        # old unused option (except for first migration from sqlite to maildir store)
        self.passdb_path = Path(params.get("passdb_path", "/home/vmail/passdb.sqlite"))

    def _getbytefile(self):
        return open(self._inipath, "rb")

    def get_user(self, addr) -> User:
        if not addr or "@" not in addr or "/" in addr:
            raise ValueError(f"invalid address {addr!r}")

        maildir = self.mailboxes_dir.joinpath(addr)
        password_path = maildir.joinpath("password")

        return User(maildir, addr, password_path, uid="vmail", gid="vmail")


def write_initial_config(inipath, mail_domain, overrides):
    """Write out default config file, using the specified config value overrides."""
    content = get_default_config_content(mail_domain, **overrides)
    inipath.write_text(content)


def get_default_config_content(mail_domain, **overrides):
    from importlib.resources import files

    inidir = files(__package__).joinpath("ini")
    source_inipath = inidir.joinpath("chatmail.ini.f")
    content = source_inipath.read_text().format(mail_domain=mail_domain)

    # apply config overrides
    new_lines = []
    extra = overrides.copy()
    for line in content.split("\n"):
        new_line = line.strip()
        if new_line and new_line[0] not in "#[":
            name, value = map(str.strip, new_line.split("=", maxsplit=1))
            value = extra.pop(name, value)
            new_line = f"{name} = {value}"
        new_lines.append(new_line)

    for name, value in extra.items():
        new_line = f"{name} = {value}"
        new_lines.append(new_line)

    content = "\n".join(new_lines)

    # apply testrun privacy overrides

    if mail_domain.endswith(".testrun.org"):
        override_inipath = inidir.joinpath("override-testrun.ini")
        privacy = iniconfig.IniConfig(override_inipath)["privacy"]
        lines = []
        for line in content.split("\n"):
            for key, value in privacy.items():
                value_lines = value.format(mail_domain=mail_domain).strip().split("\n")
                if not line.startswith(f"{key} =") or not value_lines:
                    continue
                if len(value_lines) == 1:
                    lines.append(f"{key} = {value}")
                else:
                    lines.append(f"{key} =")
                    for vl in value_lines:
                        lines.append(f"    {vl}")
                break
            else:
                lines.append(line)
        content = "\n".join(lines)
    return content
