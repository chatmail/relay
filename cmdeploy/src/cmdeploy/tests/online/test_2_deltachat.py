import ipaddress
import re
import time

import imap_tools
import pytest
import requests

from cmdeploy.remote import rshell
from cmdeploy.sshexec import SSHExec


@pytest.fixture
def imap_mailbox(cmfactory):
    (ac1,) = cmfactory.get_online_accounts(1)
    user = ac1.get_config("addr")
    password = ac1.get_config("mail_pw")
    mailbox = imap_tools.MailBox(user.split("@")[1])
    mailbox.login(user, password)
    return mailbox


class TestMetadataTokens:
    "Tests that use Metadata extension for storing tokens"

    def test_set_get_metadata(self, imap_mailbox):
        "set and get metadata token for an account"
        client = imap_mailbox.client
        client.send(b'a01 SETMETADATA INBOX (/private/devicetoken "1111" )\n')
        res = client.readline()
        assert b"OK Setmetadata completed" in res

        client.send(b"a02 GETMETADATA INBOX /private/devicetoken\n")
        res = client.readline()
        assert res[:1] == b"*"
        res = client.readline().strip().rstrip(b")")
        assert res == b"1111"
        assert b"Getmetadata completed" in client.readline()

        client.send(b'a01 SETMETADATA INBOX (/private/devicetoken "2222" )\n')
        res = client.readline()
        assert b"OK Setmetadata completed" in res

        client.send(b"a02 GETMETADATA INBOX /private/devicetoken\n")
        res = client.readline()
        assert res[:1] == b"*"
        res = client.readline().strip().rstrip(b")")
        assert res == b"1111 2222"
        assert b"Getmetadata completed" in client.readline()


class TestEndToEndDeltaChat:
    "Tests that use Delta Chat accounts on the chat mail instance."

    def test_one_on_one(self, cmfactory, lp):
        """Test that a DC account can send a message to a second DC account
        on the same chat-mail instance."""
        ac1, ac2 = cmfactory.get_online_accounts(2)
        chat = cmfactory.get_accepted_chat(ac1, ac2)
        chat.send_text("message0")

        lp.sec("wait for ac2 to receive message")
        msg2 = ac2._evtracker.wait_next_incoming_message()
        assert msg2.text == "message0"

    def test_exceed_quota(
        self, cmfactory, lp, tmpdir, remote, chatmail_config, sshdomain
    ):
        """This is a very slow test as it needs to upload >100MB of mail data
        before quota is exceeded, and thus depends on the speed of the upload.
        """
        ac1, ac2 = cmfactory.get_online_accounts(2)
        chat = cmfactory.get_accepted_chat(ac1, ac2)

        user = ac2.get_config("configured_addr")

        def parse_size_limit(limit: str) -> int:
            """Parse a size limit and return the number of bytes as integer.

            Example input: 100M, 2.4T, 500 K
            """
            units = {"B": 1, "K": 2**10, "M": 2**20, "G": 2**30, "T": 2**40}
            size = re.sub(r"([KMGT])", r" \1", limit.upper())
            number, unit = [string.strip() for string in size.split()]
            return int(float(number) * units[unit])

        quota = parse_size_limit(chatmail_config.max_mailbox_size)

        lp.sec(f"filling remote inbox for {user}")
        fn = f"7743102289.M843172P2484002.c20,S={quota},W=2398:2,"
        path = chatmail_config.mailboxes_dir.joinpath(user, "cur", fn)
        sshexec = SSHExec(sshdomain)
        sshexec(call=rshell.write_numbytes, kwargs=dict(path=str(path), num=120))
        res = sshexec(call=rshell.dovecot_recalc_quota, kwargs=dict(user=user))
        assert res["percent"] >= 100

        lp.sec("ac2: check quota is triggered")

        starting = True
        for line in remote.iter_output("journalctl -n0 -f -u dovecot"):
            if starting:
                chat.send_text("hello")
                starting = False
            if user not in line:
                # print(line)
                continue
            if "quota exceeded" in line:
                return

    def test_securejoin(self, cmfactory, lp, maildomain2):
        ac1 = cmfactory.new_online_configuring_account(cache=False)
        cmfactory.switch_maildomain(maildomain2)
        ac2 = cmfactory.new_online_configuring_account(cache=False)
        cmfactory.bring_accounts_online()

        lp.sec("ac1: create QR code and let ac2 scan it, starting the securejoin")
        qr = ac1.get_setup_contact_qr()

        lp.sec("ac2: start QR-code based setup contact protocol")
        ch = ac2.qr_setup_contact(qr)
        assert ch.id >= 10
        ac1._evtracker.wait_securejoin_inviter_progress(1000)

    def test_read_receipts_between_instances(self, cmfactory, lp, maildomain2):
        ac1 = cmfactory.new_online_configuring_account(cache=False)
        cmfactory.switch_maildomain(maildomain2)
        ac2 = cmfactory.new_online_configuring_account(cache=False)
        cmfactory.bring_accounts_online()

        lp.sec("setup encrypted comms between ac1 and ac2 on different instances")
        qr = ac1.get_setup_contact_qr()
        ch = ac2.qr_setup_contact(qr)
        assert ch.id >= 10
        ac1._evtracker.wait_securejoin_inviter_progress(1000)

        lp.sec("ac1 sends a message and ac2 marks it as seen")
        chat = ac1.create_chat(ac2)
        msg = chat.send_text("hi")
        m = ac2._evtracker.wait_next_incoming_message()
        m.mark_seen()
        # we can only indirectly wait for mark-seen to cause an smtp-error
        lp.sec("try to wait for markseen to complete and check error states")
        deadline = time.time() + 3.1
        while time.time() < deadline:
            msgs = m.chat.get_messages()
            for msg in msgs:
                assert "error" not in m.get_message_info()
            time.sleep(1)


def test_hide_senders_ip_address(cmfactory):
    public_ip = requests.get("http://icanhazip.com").content.decode().strip()
    assert ipaddress.ip_address(public_ip)

    user1, user2 = cmfactory.get_online_accounts(2)
    chat = cmfactory.get_accepted_chat(user1, user2)

    chat.send_text("testing submission header cleanup")
    user2._evtracker.wait_next_incoming_message()
    user2.direct_imap.select_folder("Inbox")
    msg = user2.direct_imap.get_all_messages()[0]
    assert public_ip not in msg.obj.as_string()
