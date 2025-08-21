import logging
import sys
import time
from contextlib import contextmanager

from .config import read_config
from .dictproxy import DictProxy
from .filedict import FileDict
from .notifier import Notifier
from .turnserver import turn_credentials


def _is_valid_token_timestamp(timestamp, now):
    # Token if invalid after 90 days
    # or if the timestamp is in the future.
    return timestamp > now - 3600 * 24 * 90 and timestamp < now + 60


class Metadata:
    # each SETMETADATA on this key appends to dictionary
    # mapping of unique device tokens
    # which only ever get removed if the upstream indicates the token is invalid
    DEVICETOKEN_KEY = "devicetoken"

    def __init__(self, vmail_dir):
        self.vmail_dir = vmail_dir

    def get_metadata_dict(self, addr):
        return FileDict(self.vmail_dir / addr / "metadata.json")

    @contextmanager
    def _modify_tokens(self, addr):
        with self.get_metadata_dict(addr).modify() as data:
            tokens = data.setdefault(self.DEVICETOKEN_KEY, {})
            now = int(time.time())
            if isinstance(tokens, list):
                data[self.DEVICETOKEN_KEY] = tokens = {t: now for t in tokens}

            expired_tokens = [
                token
                for token, timestamp in tokens.items()
                if not _is_valid_token_timestamp(tokens[token], now)
            ]
            for expired_token in expired_tokens:
                del tokens[expired_token]

            yield tokens

    def add_token_to_addr(self, addr, token):
        with self._modify_tokens(addr) as tokens:
            tokens[token] = int(time.time())

    def remove_token_from_addr(self, addr, token):
        with self._modify_tokens(addr) as tokens:
            if token in tokens:
                del tokens[token]

    def get_tokens_for_addr(self, addr):
        mdict = self.get_metadata_dict(addr).read()
        tokens = mdict.get(self.DEVICETOKEN_KEY, {})

        now = int(time.time())
        if isinstance(tokens, dict):
            token_list = [
                token
                for token, timestamp in tokens.items()
                if _is_valid_token_timestamp(timestamp, now)
            ]
            if len(token_list) < len(tokens):
                # Some tokens have expired, remove them.
                with self._modify_tokens(addr) as _tokens:
                    pass
        else:
            token_list = []
        return token_list


class MetadataDictProxy(DictProxy):
    def __init__(self, notifier, metadata, iroh_relay=None, turn_hostname=None):
        super().__init__()
        self.notifier = notifier
        self.metadata = metadata
        self.iroh_relay = iroh_relay
        self.turn_hostname = turn_hostname

    def handle_lookup(self, parts):
        # Lpriv/43f5f508a7ea0366dff30200c15250e3/devicetoken\tlkj123poi@c2.testrun.org
        keyparts = parts[0].split("/", 2)
        if keyparts[0] == "priv":
            keyname = keyparts[2]
            addr = parts[1]
            if keyname == self.metadata.DEVICETOKEN_KEY:
                res = " ".join(self.metadata.get_tokens_for_addr(addr))
                return f"O{res}\n"
        elif keyparts[0] == "shared":
            keyname = keyparts[2]
            if (
                keyname == "vendor/vendor.dovecot/pvt/server/vendor/deltachat/irohrelay"
                and self.iroh_relay
            ):
                # Handle `GETMETADATA "" /shared/vendor/deltachat/irohrelay`
                return f"O{self.iroh_relay}\n"
            elif keyname == "vendor/vendor.dovecot/pvt/server/vendor/deltachat/turn":
                res = turn_credentials()
                port = 3478
                return f"O{self.turn_hostname}:{port}:{res}\n"

        logging.warning(f"lookup ignored: {parts!r}")
        return "N\n"

    def handle_set(self, addr, parts):
        # For documentation on key structure see
        # https://github.com/dovecot/core/blob/main/src/lib-storage/mailbox-attribute.h
        keyname = parts[1].split("/")
        value = parts[2] if len(parts) > 2 else ""
        if keyname[0] == "priv" and keyname[2] == self.metadata.DEVICETOKEN_KEY:
            self.metadata.add_token_to_addr(addr, value)
            return True
        elif keyname[0] == "priv" and keyname[2] == "messagenew":
            self.notifier.new_message_for_addr(addr, self.metadata)
            return True

        return False


def main():
    socket, config_path = sys.argv[1:]

    config = read_config(config_path)
    iroh_relay = config.iroh_relay
    mail_domain = config.mail_domain

    vmail_dir = config.mailboxes_dir
    if not vmail_dir.exists():
        logging.error("vmail dir does not exist: %r", vmail_dir)
        return 1

    queue_dir = vmail_dir / "pending_notifications"
    queue_dir.mkdir(exist_ok=True)
    metadata = Metadata(vmail_dir)
    notifier = Notifier(queue_dir)
    notifier.start_notification_threads(metadata.remove_token_from_addr)

    dictproxy = MetadataDictProxy(
        notifier=notifier,
        metadata=metadata,
        iroh_relay=iroh_relay,
        turn_hostname=mail_domain,
    )

    dictproxy.serve_forever_from_socket(socket)
