#!/usr/bin/env python3
import asyncio
import base64
import binascii
import logging
import sys
import time
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from smtplib import SMTP as SMTPClient

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP

from .config import read_config

ENCRYPTION_NEEDED_523 = "523 Encryption Needed: Invalid Unencrypted Mail"


def check_openpgp_payload(payload: bytes):
    """Checks the OpenPGP payload.

    OpenPGP payload must consist only of PKESK and SKESK packets
    terminated by a single SEIPD packet.

    Returns True if OpenPGP payload is correct,
    False otherwise.

    May raise IndexError while trying to read OpenPGP packet header
    if it is truncated.
    """
    i = 0
    while i < len(payload):
        # Only OpenPGP format is allowed.
        if payload[i] & 0xC0 != 0xC0:
            return False

        packet_type_id = payload[i] & 0x3F
        i += 1

        while payload[i] >= 224 and payload[i] < 255:
            # Partial body length.
            partial_length = 1 << (payload[i] & 0x1F)
            i += 1 + partial_length

        if payload[i] < 192:
            # One-octet length.
            body_len = payload[i]
            i += 1
        elif payload[i] < 224:
            # Two-octet length.
            body_len = ((payload[i] - 192) << 8) + payload[i + 1] + 192
            i += 2
        elif payload[i] == 255:
            # Five-octet length.
            body_len = (
                (payload[i + 1] << 24)
                | (payload[i + 2] << 16)
                | (payload[i + 3] << 8)
                | payload[i + 4]
            )
            i += 5
        else:
            # Impossible, partial body length was processed above.
            return False

        i += body_len

        if i == len(payload):
            # Last packet should be
            # Symmetrically Encrypted and Integrity Protected Data Packet (SEIPD)
            #
            # This is the only place where this function may return `True`.
            return packet_type_id == 18
        elif packet_type_id not in [1, 3]:
            # All packets except the last one must be either
            # Public-Key Encrypted Session Key Packet (PKESK)
            # or
            # Symmetric-Key Encrypted Session Key Packet (SKESK)
            return False

    return False


def check_armored_payload(payload: str):
    prefix = "-----BEGIN PGP MESSAGE-----\r\n\r\n"
    if not payload.startswith(prefix):
        return False
    payload = payload.removeprefix(prefix)

    while payload.endswith("\r\n"):
        payload = payload.removesuffix("\r\n")
    suffix = "-----END PGP MESSAGE-----"
    if not payload.endswith(suffix):
        return False
    payload = payload.removesuffix(suffix)

    # Remove CRC24.
    payload = payload.rpartition("=")[0]

    try:
        payload = base64.b64decode(payload)
    except binascii.Error:
        return False

    try:
        return check_openpgp_payload(payload)
    except IndexError:
        return False


def is_securejoin(message):
    if message.get("secure-join") not in ["vc-request", "vg-request"]:
        return False
    if not message.is_multipart():
        return False
    parts_count = 0
    for part in message.iter_parts():
        parts_count += 1
        if parts_count > 1:
            return False
        if part.is_multipart():
            return False
        if part.get_content_type() != "text/plain":
            return False

        payload = part.get_payload().strip().lower()
        if payload not in ("secure-join: vc-request", "secure-join: vg-request"):
            return False
    return True


def check_encrypted(message):
    """Check that the message is an OpenPGP-encrypted message.

    MIME structure of the message must correspond to <https://www.rfc-editor.org/rfc/rfc3156>.
    """
    if not message.is_multipart():
        return False
    if message.get_content_type() != "multipart/encrypted":
        return False
    parts_count = 0
    for part in message.iter_parts():
        # We explicitly check Content-Type of each part later,
        # but this is to be absolutely sure `get_payload()` returns string and not list.
        if part.is_multipart():
            return False

        if parts_count == 0:
            if part.get_content_type() != "application/pgp-encrypted":
                return False

            payload = part.get_payload()
            if payload.strip() != "Version: 1":
                return False
        elif parts_count == 1:
            if part.get_content_type() != "application/octet-stream":
                return False

            if not check_armored_payload(part.get_payload()):
                return False
        else:
            return False
        parts_count += 1
    return True


async def asyncmain_beforequeue(config, mode):
    if mode == "outgoing":
        port = config.filtermail_smtp_port
        handler = OutgoingBeforeQueueHandler(config)
    else:
        port = config.filtermail_smtp_port_incoming
        handler = IncomingBeforeQueueHandler(config)
    HackedController(
        handler,
        hostname="127.0.0.1",
        port=port,
        data_size_limit=config.max_message_size,
    ).start()


def recipient_matches_passthrough(recipient, passthrough_recipients):
    for addr in passthrough_recipients:
        if recipient == addr:
            return True
        if addr[0] == "@" and recipient.endswith(addr):
            return True
    return False


class HackedController(Controller):
    def factory(self):
        return SMTPDiscardRCPTO_options(self.handler, **self.SMTP_kwargs)


class SMTPDiscardRCPTO_options(SMTP):
    def _getparams(self, params):
        # aiosmtpd's SMTP daemon fails to handle a request if there are RCPT TO options
        # We just ignore them for our incoming filtermail purposes
        if len(params) == 1 and params[0].startswith("ORCPT"):
            return {}
        return super()._getparams(params)


class OutgoingBeforeQueueHandler:
    def __init__(self, config):
        self.config = config
        self.send_rate_limiter = SendRateLimiter()

    async def handle_MAIL(self, server, session, envelope, address, mail_options):
        logging.info(f"handle_MAIL from {address}")
        envelope.mail_from = address
        max_sent = self.config.max_user_send_per_minute
        if not self.send_rate_limiter.is_sending_allowed(address, max_sent):
            return f"450 4.7.1: Too much mail from {address}"

        parts = envelope.mail_from.split("@")
        if len(parts) != 2:
            return f"500 Invalid from address <{envelope.mail_from!r}>"

        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        logging.info("handle_DATA before-queue")
        error = self.check_DATA(envelope)
        if error:
            return error
        logging.info("re-injecting the mail that passed checks")
        client = SMTPClient("localhost", self.config.postfix_reinject_port)
        client.sendmail(
            envelope.mail_from, envelope.rcpt_tos, envelope.original_content
        )
        return "250 OK"

    def check_DATA(self, envelope):
        """the central filtering function for e-mails."""
        logging.info(f"Processing DATA message from {envelope.mail_from}")

        message = BytesParser(policy=policy.default).parsebytes(envelope.content)
        mail_encrypted = check_encrypted(message)

        _, from_addr = parseaddr(message.get("from").strip())

        if envelope.mail_from.lower() != from_addr.lower():
            return f"500 Invalid FROM <{from_addr!r}> for <{envelope.mail_from!r}>"

        if mail_encrypted or is_securejoin(message):
            print("Outgoing: Filtering encrypted mail.", file=sys.stderr)
            return

        print("Outgoing: Filtering unencrypted mail.", file=sys.stderr)

        if envelope.mail_from in self.config.passthrough_senders:
            return

        # allow self-sent Autocrypt Setup Message
        if envelope.rcpt_tos == [from_addr]:
            if message.get("subject") == "Autocrypt Setup Message":
                if message.get_content_type() == "multipart/mixed":
                    return

        passthrough_recipients = self.config.passthrough_recipients

        for recipient in envelope.rcpt_tos:
            if recipient_matches_passthrough(recipient, passthrough_recipients):
                continue

            print("Rejected unencrypted mail.", file=sys.stderr)
            return ENCRYPTION_NEEDED_523


class IncomingBeforeQueueHandler:
    def __init__(self, config):
        self.config = config

    async def handle_DATA(self, server, session, envelope):
        logging.info("handle_DATA before-queue")
        error = self.check_DATA(envelope)
        if error:
            return error
        logging.info("re-injecting the mail that passed checks")

        # the smtp daemon on reinject_port_incoming gives it to dkim milter
        # which looks at source address to determine whether to verify or sign
        client = SMTPClient(
            "localhost",
            self.config.postfix_reinject_port_incoming,
            source_address=("127.0.0.2", 0),
        )
        client.sendmail(
            envelope.mail_from, envelope.rcpt_tos, envelope.original_content
        )
        return "250 OK"

    def check_DATA(self, envelope):
        """the central filtering function for e-mails."""
        logging.info(f"Processing DATA message from {envelope.mail_from}")

        message = BytesParser(policy=policy.default).parsebytes(envelope.content)
        mail_encrypted = check_encrypted(message)

        if mail_encrypted or is_securejoin(message):
            print("Incoming: Filtering encrypted mail.", file=sys.stderr)
            return

        print("Incoming: Filtering unencrypted mail.", file=sys.stderr)

        # we want cleartext mailer-daemon messages to pass through
        # chatmail core will typically not display them as normal messages
        if message.get("auto-submitted"):
            _, from_addr = parseaddr(message.get("from").strip())
            if from_addr.lower().startswith("mailer-daemon@"):
                if message.get_content_type() == "multipart/report":
                    return

        for recipient in envelope.rcpt_tos:
            user = self.config.get_user(recipient)
            if user is None or user.is_incoming_cleartext_ok():
                continue

            print("Rejected unencrypted mail.", file=sys.stderr)
            return ENCRYPTION_NEEDED_523


class SendRateLimiter:
    def __init__(self):
        self.addr2timestamps = {}

    def is_sending_allowed(self, mail_from, max_send_per_minute):
        last = self.addr2timestamps.setdefault(mail_from, [])
        now = time.time()
        last[:] = [ts for ts in last if ts >= (now - 60)]
        if len(last) <= max_send_per_minute:
            last.append(now)
            return True
        return False


def main():
    args = sys.argv[1:]
    assert len(args) == 2
    config = read_config(args[0])
    mode = args[1]
    logging.basicConfig(level=logging.WARN)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    assert mode in ["incoming", "outgoing"]
    task = asyncmain_beforequeue(config, mode)
    loop.create_task(task)
    logging.info("entering serving loop")
    loop.run_forever()
