from pathlib import Path

import iniconfig

from chatmaild.user import User

echobot_password_path = Path("/run/echobot/password")


def read_config(inipath):
    assert Path(inipath).exists(), inipath
    cfg = iniconfig.IniConfig(inipath)
    params = cfg.sections["params"]
    default_config_content = get_default_config_content(params["mail_domain"])
    df_params = iniconfig.IniConfig("ini", data=default_config_content)["params"]
    new_params = dict(df_params.items())
    new_params.update(params)
    return Config(inipath, params=new_params)


class Config:
    def __init__(self, inipath, params):
        self._inipath = inipath
        self.mail_domain = params["mail_domain"]
        self.max_user_send_per_minute = int(params["max_user_send_per_minute"])
        self.max_mailbox_size = params["max_mailbox_size"]
        self.max_message_size = int(params.get("max_message_size", "31457280"))
        self.delete_mails_after = params["delete_mails_after"]
        self.delete_large_after = params["delete_large_after"]
        self.delete_inactive_users_after = int(params["delete_inactive_users_after"])
        self.username_min_length = int(params["username_min_length"])
        self.username_max_length = int(params["username_max_length"])
        self.password_min_length = int(params["password_min_length"])
        self.passthrough_senders = params["passthrough_senders"].split()
        self.passthrough_recipients = params["passthrough_recipients"].split()
        self.filtermail_smtp_port = int(params["filtermail_smtp_port"])
        self.filtermail_smtp_port_incoming = int(
            params["filtermail_smtp_port_incoming"]
        )
        self.postfix_reinject_port = int(params["postfix_reinject_port"])
        self.postfix_reinject_port_incoming = int(
            params["postfix_reinject_port_incoming"]
        )
        self.mtail_address = params.get("mtail_address")
        self.disable_ipv6 = params.get("disable_ipv6", "false").lower() == "true"
        self.imap_rawlog = params.get("imap_rawlog", "false").lower() == "true"
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
        if addr.startswith("echo@"):
            password_path = echobot_password_path
        else:
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
