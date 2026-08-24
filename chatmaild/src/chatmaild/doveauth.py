"""Create chatmail addresses on first login.

Dovecot only asks us about addresses it does not already find in the mailbox:
the auth.lua we deploy with dovecot (cmdeploy/src/cmdeploy/dovecot/auth.lua.j2)
verifies existing users itself against a mailbox password file,
and HTTP-POSTs everything else to the /create endpoint implemented in this module.
"""

import logging
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import crypt_r
except ImportError:
    import crypt as crypt_r

from .config import Config, read_config
from .migrate_db import migrate_from_db_to_maildir
from .syslimits import has_sufficient_resources

NOCREATE_FILE = "/etc/chatmail-nocreate"
VALID_LOCALPART_RE = re.compile(r"^[a-z0-9._-]+$")


def encrypt_password(password: str):
    # https://doc.dovecot.org/2.3/configuration_manual/authentication/password_schemes/
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

    if not VALID_LOCALPART_RE.match(localpart):
        logging.warning("localpart %r contains invalid characters", localpart)
        return False

    return True


def verify_password(stored, cleartext_password) -> bool:
    if stored.startswith("{"):
        stored = stored.split("}", 1)[1]
    return crypt_r.crypt(cleartext_password, stored) == stored


class DoveAuth:
    def __init__(self, config):
        self.config = config
        self.creation_lock = threading.Lock()

    def create_user(self, addr, cleartext_password) -> bool:
        """Create the address, or verify the password if it exists already."""
        config = self.config
        if not addr.endswith(f"@{config.mail_domain}"):
            logging.warning("address not in mail domain: %r", addr)
            return False
        try:
            user = config.get_user(addr)
        except ValueError:
            logging.warning("invalid address: %r", addr)
            return False
        with self.creation_lock:
            passhash = user.get_password_hash()
            if passhash is not None:
                # a concurrent first login may have just created the address
                return verify_password(passhash, cleartext_password)
            if not is_allowed_to_create(config, addr, cleartext_password):
                return False
            if not has_sufficient_resources(config):
                return False
            user.set_password(encrypt_password(cleartext_password))
        # mtail counts created_accounts off this exact line
        print(f"Created address: {addr}", file=sys.stderr)
        return True


class CreateHandler(BaseHTTPRequestHandler):
    """Answer POST /create requests from dovecot's auth.lua, body `addr\\tpassword`.

    The body must be UTF-8 and only the first tab separates the fields,
    so a password may itself contain tabs.
    Any non-UTF8 or \\0 bytes in the body fail the request.

    Addresses are ASCII: dovecot refuses any login name outside its
    auth_username_chars before auth.lua ever sees it.

    Dovecot hands auth.lua the exact password bytes the client sent;
    decoding and re-encoding UTF-8 is byte-identical,
    so dovecot's password_verify later recomputes the same hash crypt() stores here.
    """

    protocol_version = "HTTP/1.1"  # dovecot's HTTP client reuses connections

    max_body_len = 512  # an address and a password

    def do_POST(self):
        if self.path != "/create":
            self.reply(404)
            return
        length = self.body_length()
        if length is None:
            self.reply(400)
            return
        body = self.rfile.read(length)
        try:
            addr, _, password = body.decode("utf-8").partition("\t")
        except UnicodeDecodeError:
            self.reply(400)
            return
        if "\0" in addr or "\0" in password:
            self.reply(400)
            return
        self.reply(200 if self.server.doveauth.create_user(addr, password) else 403)

    def body_length(self):
        try:
            length = int(self.headers["Content-Length"])
        except (TypeError, ValueError):
            return None
        return length if 0 <= length <= self.max_body_len else None

    def reply(self, status):
        self.send_response(status)
        self.send_header("Content-Length", "0")
        if status != 200:
            # Just close on any failure, as body might not be fully read.
            # It's anyway cheap to re-establish http localhost without TLS.
            self.send_header("Connection", "close")
        self.end_headers()

    def log_message(self, format, *args):
        # the per-request access log would only duplicate our own stderr lines
        pass


class DoveAuthServer(ThreadingHTTPServer):
    # a burst of first-time logins (e.g. from CI) must not overflow
    # the accept queue, see https://github.com/chatmail/relay/issues/436
    request_queue_size = 1000

    def __init__(self, config, port):
        super().__init__(("127.0.0.1", port), CreateHandler)
        self.doveauth = DoveAuth(config)


def main():
    (cfgpath,) = sys.argv[1:]
    config = read_config(cfgpath)

    migrate_from_db_to_maildir(config)

    server = DoveAuthServer(config, config.doveauth_http_port)
    server.serve_forever()
