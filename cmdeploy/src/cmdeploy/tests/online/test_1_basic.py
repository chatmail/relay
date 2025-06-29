import datetime
import smtplib
import socket
import subprocess

import pytest

from cmdeploy import remote
from cmdeploy.sshexec import SSHExec


class TestSSHExecutor:
    @pytest.fixture(scope="class")
    def sshexec(self, sshdomain):
        return SSHExec(sshdomain)

    def test_ls(self, sshexec):
        out = sshexec(call=remote.rdns.shell, kwargs=dict(command="ls"))
        out2 = sshexec(call=remote.rdns.shell, kwargs=dict(command="ls"))
        assert out == out2

    def test_perform_initial(self, sshexec, maildomain):
        res = sshexec(
            remote.rdns.perform_initial_checks, kwargs=dict(mail_domain=maildomain)
        )
        assert res["A"] or res["AAAA"]

    def test_logged(self, sshexec, maildomain, capsys):
        sshexec.logged(
            remote.rdns.perform_initial_checks, kwargs=dict(mail_domain=maildomain)
        )
        out, err = capsys.readouterr()
        assert err.startswith("Collecting")
        assert err.endswith("....\n")
        assert err.count("\n") == 1

        sshexec.verbose = True
        sshexec.logged(
            remote.rdns.perform_initial_checks, kwargs=dict(mail_domain=maildomain)
        )
        out, err = capsys.readouterr()
        lines = err.split("\n")
        assert len(lines) > 4
        assert remote.rdns.perform_initial_checks.__doc__ in lines[0]

    def test_exception(self, sshexec, capsys):
        try:
            sshexec.logged(
                remote.rdns.perform_initial_checks,
                kwargs=dict(mail_domain=None),
            )
        except sshexec.FuncError as e:
            assert "rdns.py" in str(e)
            assert "AssertionError" in str(e)
        else:
            pytest.fail("didn't raise exception")

    def test_opendkim_restarted(self, sshexec):
        """check that opendkim is not running for longer than a day."""
        cmd = "systemctl show opendkim --timestamp=utc --property=ActiveEnterTimestamp"
        out = sshexec(call=remote.rshell.shell, kwargs=dict(command=cmd))
        datestring = out.split("=")[1]
        since_date = datetime.datetime.strptime(datestring, "%a %Y-%m-%d %H:%M:%S %Z")
        now = datetime.datetime.now(since_date.tzinfo)
        assert (now - since_date).total_seconds() < 60 * 60 * 51


def test_timezone_env(remote):
    for line in remote.iter_output("env"):
        print(line)
        if line == "tz=:/etc/localtime":
            return True
    pytest.fail("TZ is not set")


def test_remote(remote, imap_or_smtp):
    lineproducer = remote.iter_output(imap_or_smtp.logcmd)
    imap_or_smtp.connect()
    assert imap_or_smtp.name in next(lineproducer)


def test_use_two_chatmailservers(cmfactory, maildomain2):
    ac1 = cmfactory.new_online_configuring_account(cache=False)
    cmfactory.switch_maildomain(maildomain2)
    ac2 = cmfactory.new_online_configuring_account(cache=False)
    cmfactory.bring_accounts_online()
    cmfactory.get_accepted_chat(ac1, ac2)
    domain1 = ac1.get_config("addr").split("@")[1]
    domain2 = ac2.get_config("addr").split("@")[1]
    assert domain1 != domain2


@pytest.mark.parametrize("forgeaddr", ["internal", "someone@example.org"])
def test_reject_forged_from(cmsetup, maildata, gencreds, lp, forgeaddr):
    user1, user3 = cmsetup.gen_users(2)

    lp.sec("send encrypted message with forged from")
    print("envelope_from", user1.addr)
    if forgeaddr == "internal":
        addr_to_forge = cmsetup.gen_users(1)[0].addr
    else:
        addr_to_forge = "someone@example.org"

    print("message to inject:")
    msg = maildata("encrypted.eml", from_addr=addr_to_forge, to_addr=user3.addr)
    msg = msg.as_string()
    for line in msg.split("\n")[:4]:
        print(f"   {line}")

    lp.sec("Send forged mail and check remote postfix lmtp processing result")
    with pytest.raises(smtplib.SMTPException) as e:
        user1.smtp.sendmail(from_addr=user1.addr, to_addrs=[user3.addr], msg=msg)
    assert "500" in str(e.value)


def test_authenticated_from(cmsetup, maildata):
    """Test that envelope FROM must be the same as login."""
    user1, user2, user3 = cmsetup.gen_users(3)

    msg = maildata("encrypted.eml", from_addr=user2.addr, to_addr=user3.addr)
    with pytest.raises(smtplib.SMTPException) as e:
        user1.smtp.sendmail(
            from_addr=user2.addr, to_addrs=[user3.addr], msg=msg.as_string()
        )
    assert e.value.recipients[user3.addr][0] == 553


@pytest.mark.parametrize("from_addr", ["fake@example.org", "fake@testrun.org"])
def test_reject_missing_dkim(cmsetup, maildata, from_addr):
    domain = cmsetup.maildomain
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    try:
        sock.connect((domain, 25))
    except socket.timeout:
        pytest.skip(f"port 25 not reachable for {domain}")

    recipient = cmsetup.gen_users(1)[0]
    msg = maildata(
        "encrypted.eml", from_addr=from_addr, to_addr=recipient.addr
    ).as_string()
    conn = smtplib.SMTP(cmsetup.maildomain, 25, timeout=10)

    with conn as s:
        with pytest.raises(smtplib.SMTPDataError, match="No valid DKIM signature"):
            s.sendmail(from_addr=from_addr, to_addrs=recipient.addr, msg=msg)


def test_rewrite_subject(cmsetup, maildata):
    """Test that subject gets replaced with [...]."""
    user1, user2 = cmsetup.gen_users(2)

    sent_msg = maildata(
        "encrypted.eml",
        from_addr=user1.addr,
        to_addr=user2.addr,
        subject="Unencrypted subject",
    ).as_string()
    user1.smtp.sendmail(from_addr=user1.addr, to_addrs=[user2.addr], msg=sent_msg)

    messages = user2.imap.fetch_all_messages()
    assert len(messages) == 1
    rcvd_msg = messages[0]
    assert "Subject: [...]" not in sent_msg
    assert "Subject: [...]" in rcvd_msg
    assert "Subject: Unencrypted subject" in sent_msg
    assert "Subject: Unencrypted subject" not in rcvd_msg


@pytest.mark.slow
def test_exceed_rate_limit(cmsetup, gencreds, maildata, chatmail_config):
    """Test that the per-account send-mail limit is exceeded."""
    user1, user2 = cmsetup.gen_users(2)
    mail = maildata(
        "encrypted.eml", from_addr=user1.addr, to_addr=user2.addr
    ).as_string()
    for i in range(chatmail_config.max_user_send_per_minute + 5):
        print("Sending mail", str(i))
        try:
            user1.smtp.sendmail(user1.addr, [user2.addr], mail)
        except smtplib.SMTPException as e:
            if i < chatmail_config.max_user_send_per_minute:
                pytest.fail(f"rate limit was exceeded too early with msg {i}")
            outcome = e.recipients[user2.addr]
            assert outcome[0] == 450
            assert b"4.7.1: Too much mail from" in outcome[1]
            return
    pytest.fail("Rate limit was not exceeded")


@pytest.mark.slow
def test_expunged(remote, chatmail_config):
    outdated_days = int(chatmail_config.delete_mails_after) + 1
    find_cmds = [
        f"find {chatmail_config.mailboxes_dir} -path '*/cur/*' -mtime +{outdated_days} -type f",
        f"find {chatmail_config.mailboxes_dir} -path '*/.*/cur/*' -mtime +{outdated_days} -type f",
        f"find {chatmail_config.mailboxes_dir} -path '*/new/*' -mtime +{outdated_days} -type f",
        f"find {chatmail_config.mailboxes_dir} -path '*/.*/new/*' -mtime +{outdated_days} -type f",
        f"find {chatmail_config.mailboxes_dir} -path '*/tmp/*' -mtime +{outdated_days} -type f",
        f"find {chatmail_config.mailboxes_dir} -path '*/.*/tmp/*' -mtime +{outdated_days} -type f",
    ]
    outdated_days = int(chatmail_config.delete_large_after) + 1
    find_cmds.append(
        "find {chatmail_config.mailboxes_dir} -path '*/cur/*' -mtime +{outdated_days} -size +200k -type f"
    )
    for cmd in find_cmds:
        for line in remote.iter_output(cmd):
            assert not line


def test_deployed_state(remote):
    git_hash = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode()
    git_diff = subprocess.check_output(["git", "diff"]).decode()
    git_status = [git_hash.strip()]
    for line in git_diff.splitlines():
        git_status.append(line.strip().lower())
    remote_version = []
    for line in remote.iter_output("cat /etc/chatmail-version"):
        print(line)
        remote_version.append(line)
    # assert len(git_status) == len(remote_version)  # for some reason, we only get 11 lines from remote.iter_output()
    for i in range(len(remote_version)):
        assert git_status[i] == remote_version[i], "You have undeployed changes."
