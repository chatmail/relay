import json
import logging
import os
import sys

try:
    import crypt_r
except ImportError:
    import crypt as crypt_r

from .config import Config, read_config
from .dictproxy import DictProxy
from .migrate_db import migrate_from_db_to_maildir

NOCREATE_FILE = "/etc/chatmail-nocreate"


def encrypt_password(password: str):
    # https://doc.dovecot.org/configuration_manual/authentication/password_schemes/
    passhash = crypt_r.crypt(password, crypt_r.METHOD_SHA512)
    return "{SHA512-CRYPT}" + passhash


def is_allowed_to_create(config: Config, user, cleartext_password) -> bool:
    """Return True if user and password are admissable."""
    if os.path.exists(NOCREATE_FILE):
        logging.warning(f"blocked account creation because {NOCREATE_FILE!r} exists.")
        return False

    if len(cleartext_password) < config.password_min_length:
        logging.warning(
            "Password needs to be at least %s characters long",
            config.password_min_length,
        )
        return False

    parts = user.split("@")
    if len(parts) != 2:
        logging.warning(f"user {user!r} is not a proper e-mail address")
        return False
    localpart, domain = parts

    if (
        len(localpart) > config.username_max_length
        or len(localpart) < config.username_min_length
    ):
        logging.warning(
            "localpart %s has to be between %s and %s chars long",
            localpart,
            config.username_min_length,
            config.username_max_length,
        )
        return False

    return True


def split_and_unescape(s):
    """Split strings using double quote as a separator and backslash as escape character
    into parts."""

    out = ""
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            # Skip escape character.
            i += 1

            # This will raise IndexError if there is no character
            # after escape character. This is expected
            # as this is an invalid input.
            out += s[i]
        elif c == '"':
            # Separator
            yield out
            out = ""
        else:
            out += c
        i += 1
    yield out


class AuthDictProxy(DictProxy):
    def __init__(self, config):
        super().__init__()
        self.config = config

    def handle_lookup(self, parts):
        # Dovecot <2.3.17 has only one part,
        # do not attempt to read any other parts for compatibility.
        keyname = parts[0]

        namespace, type, args = keyname.split("/", 2)
        args = list(split_and_unescape(args))

        config = self.config
        reply_command = "F"
        res = ""
        if namespace == "shared":
            if type == "userdb":
                user = args[0]
                if user.endswith(f"@{config.mail_domain}"):
                    res = self.lookup_userdb(user)
                if res:
                    reply_command = "O"
                else:
                    reply_command = "N"
            elif type == "passdb":
                user = args[1]
                if user.endswith(f"@{config.mail_domain}"):
                    res = self.lookup_passdb(user, cleartext_password=args[0])
                if res:
                    reply_command = "O"
                else:
                    reply_command = "N"
        json_res = json.dumps(res) if res else ""
        return f"{reply_command}{json_res}\n"

    def handle_iterate(self, parts):
        # example: I0\t0\tshared/userdb/
        if parts[2] == "shared/userdb/":
            result = "".join(
                f"Oshared/userdb/{user}\t\n" for user in self.iter_userdb()
            )
            return f"{result}\n"

    def iter_userdb(self) -> list:
        """Get a list of all user addresses."""
        return [x for x in os.listdir(self.config.mailboxes_dir) if "@" in x]

    def lookup_userdb(self, addr):
        return self.config.get_user(addr).get_userdb_dict()

    def lookup_passdb(self, addr, cleartext_password):
        user = self.config.get_user(addr)
        userdata = user.get_userdb_dict()
        if userdata:
            return userdata
        if not is_allowed_to_create(self.config, addr, cleartext_password):
            return

        user.set_password(encrypt_password(cleartext_password))
        print(f"Created address: {addr}", file=sys.stderr)
        return user.get_userdb_dict()


def main():
    socket, cfgpath = sys.argv[1:]
    config = read_config(cfgpath)

    migrate_from_db_to_maildir(config)

    dictproxy = AuthDictProxy(config=config)

    dictproxy.serve_forever_from_socket(socket)
