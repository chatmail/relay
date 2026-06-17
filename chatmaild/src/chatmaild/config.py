import ipaddress
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
        params = dict(params)
        raw_domain = params.pop("mail_domain")
        self.mail_domain_bare = raw_domain

        if is_valid_ipv4(raw_domain):
            self.ipv4_relay = raw_domain
            self.mail_domain = f"[{raw_domain}]"
            self.postfix_myhostname = ipaddress.IPv4Address(raw_domain).reverse_pointer
        else:
            self.ipv4_relay = None
            self.mail_domain = raw_domain
            self.postfix_myhostname = raw_domain

        self.max_user_send_per_minute = int(params.pop("max_user_send_per_minute", 60))
        self.max_user_send_burst_size = int(params.pop("max_user_send_burst_size", 10))
        self.max_mailbox_size = params.pop("max_mailbox_size", "500M")
        self.max_message_size = int(params.pop("max_message_size", 31457280))
        self.delete_mails_after = params.pop("delete_mails_after", "20")
        self.delete_large_after = params.pop("delete_large_after", "7")
        self.delete_inactive_users_after = int(
            params.pop("delete_inactive_users_after", 90)
        )
        self.username_min_length = int(params.pop("username_min_length", 9))
        self.username_max_length = int(params.pop("username_max_length", 9))
        self.password_min_length = int(params.pop("password_min_length", 9))
        self.www_folder = params.pop("www_folder", "")
        self.filtermail_smtp_port = int(params.pop("filtermail_smtp_port", "10080"))
        self.filtermail_smtp_port_incoming = int(
            params.pop("filtermail_smtp_port_incoming", "10081")
        )
        self.filtermail_http_port_incoming = int(
            params.pop("filtermail_http_port_incoming", "10082")
        )
        self.filtermail_lmtp_port_transport = int(
            params.pop("filtermail_lmtp_port_transport", "10083")
        )
        self.postfix_reinject_port = int(params.pop("postfix_reinject_port", "10025"))
        self.postfix_reinject_port_incoming = int(
            params.pop("postfix_reinject_port_incoming", "10026")
        )
        self.mtail_address = params.pop("mtail_address", None)
        self.disable_ipv6 = params.pop("disable_ipv6", "false").lower() == "true"
        self.acme_email = params.pop("acme_email", "")
        self.imap_rawlog = params.pop("imap_rawlog", "false").lower() == "true"
        self.imap_compress = params.pop("imap_compress", "false").lower() == "true"
        self.turn_socket_path = params.pop(
            "turn_socket_path", "/run/chatmail-turn/turn.socket"
        )
        iroh_relay = params.pop("iroh_relay", None)
        if iroh_relay is None:
            self.iroh_relay = "https://" + raw_domain
            self.enable_iroh_relay = True
        else:
            self.iroh_relay = iroh_relay.strip()
            self.enable_iroh_relay = False
        self.privacy_postal = params.pop("privacy_postal", None)
        self.privacy_mail = params.pop("admin_contact", params.pop("privacy_mail", None))
        self.privacy_pdo = params.pop("privacy_pdo", None)
        self.privacy_supervisor = params.pop("privacy_supervisor", None)

        # TLS certificate management.
        # If tls_external_cert_and_key is set, use externally managed certs.
        # Otherwise derived from the domain name:
        # - Domains starting with "_" use self-signed certificates
        # - All other domains use ACME.
        external = params.pop("tls_external_cert_and_key", "").strip()

        if external:
            parts = external.split()
            if len(parts) != 2:
                raise ValueError(
                    "tls_external_cert_and_key must have two space-separated"
                    " paths: CERT_PATH KEY_PATH"
                )
            self.tls_cert_mode = "external"
            self.tls_cert_path, self.tls_key_path = parts
        elif raw_domain.startswith("_") or self.ipv4_relay:
            self.tls_cert_mode = "self"
            self.tls_cert_path = "/etc/ssl/certs/mailserver.pem"
            self.tls_key_path = "/etc/ssl/private/mailserver.key"
        else:
            self.tls_cert_mode = "acme"
            self.tls_cert_path = f"/var/lib/acme/live/{raw_domain}/fullchain"
            self.tls_key_path = f"/var/lib/acme/live/{raw_domain}/privkey"

        # deprecated option
        mbdir = params.pop("mailboxes_dir", f"/home/vmail/mail/{raw_domain}")
        self.mailboxes_dir = Path(mbdir.strip())

        # old unused option (except for first migration from sqlite to maildir store)
        self.passdb_path = Path(params.pop("passdb_path", "/home/vmail/passdb.sqlite"))
        self._unused_keys = list(params)

    @property
    def max_mailbox_size_mb(self):
        """Return max_mailbox_size as an integer in megabytes."""
        return parse_size_mb(self.max_mailbox_size)

    def _getbytefile(self):
        return open(self._inipath, "rb")

    def get_user(self, addr) -> User:
        if not addr or "@" not in addr or "/" in addr:
            raise ValueError(f"invalid address {addr!r}")

        maildir = self.mailboxes_dir.joinpath(addr)
        password_path = maildir.joinpath("password")

        return User(maildir, addr, password_path, uid="vmail", gid="vmail")


def parse_size_mb(limit):
    """Parse a size string like ``500M`` or ``2G`` and return megabytes."""
    value = limit.strip().upper().removesuffix("B")
    if value.endswith("G"):
        return int(value[:-1]) * 1024
    if value.endswith("M"):
        return int(value[:-1])
    return int(value)


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
    return "\n".join(new_lines)


def is_valid_ipv4(address: str) -> bool:
    """Check if a mail_domain is an IPv4 address."""
    try:
        ipaddress.IPv4Address(address)
        return True
    except ValueError:
        return False
