import queue
import smtplib
import threading

import pytest
from chatmaild.config import read_config

from cmdeploy.cmdeploy import main


def test_init(tmp_path, maildomain):
    inipath = tmp_path.joinpath("chatmail.ini")
    main(["init", "--config", str(inipath), maildomain])
    config = read_config(inipath)
    assert config.mail_domain == maildomain


def test_capabilities(imap):
    imap.connect()
    capas = imap.conn.capabilities
    assert "XCHATMAIL" in capas
    assert "XDELTAPUSH" in capas


def test_login_basic_functioning(imap_or_smtp, gencreds, lp):
    """Test a) that an initial login creates a user automatically
    and b) verify we can also login a second time with the same password
    and c) that using a different password fails the login."""
    user, password = gencreds()
    lp.sec(f"login first time with {user} {password}")
    imap_or_smtp.connect()
    imap_or_smtp.login(user, password)
    lp.indent("success")

    lp.sec(f"reconnect and login second time {user} {password}")
    imap_or_smtp.connect()
    imap_or_smtp.login(user, password)
    imap_or_smtp.connect()
    lp.sec("success")

    lp.sec(f"reconnect and verify wrong password fails {user} ")
    imap_or_smtp.connect()
    with pytest.raises(imap_or_smtp.AuthError):
        imap_or_smtp.login(user, password + "wrong")

    lp.sec("creating users with a short password is not allowed")
    user, _password = gencreds()
    with pytest.raises(imap_or_smtp.AuthError):
        imap_or_smtp.login(user, "admin")


def test_login_same_password(imap_or_smtp, gencreds):
    """Test two different users logging in with the same password
    to ensure that authentication process does not confuse the users
    by using only the password hash as a key.
    """
    user1, password1 = gencreds()
    user2, _ = gencreds()
    imap_or_smtp.connect()
    imap_or_smtp.login(user1, password1)
    imap_or_smtp.connect()
    imap_or_smtp.login(user2, password1)


def test_concurrent_logins_same_account(
    make_imap_connection, make_smtp_connection, gencreds
):
    """Test concurrent smtp and imap logins
    and check remote server succeeds on each connection.
    """
    user1, password1 = gencreds()
    login_results = queue.Queue()

    def login_smtp_imap(smtp, imap):
        try:
            imap.login(user1, password1)
        except Exception:
            login_results.put(False)
        else:
            login_results.put(True)

    conns = [(make_smtp_connection(), make_imap_connection()) for i in range(10)]

    for args in conns:
        thread = threading.Thread(target=login_smtp_imap, args=args, daemon=True)
        thread.start()

    for _ in conns:
        assert login_results.get()


def test_no_vrfy(chatmail_config):
    domain = chatmail_config.mail_domain

    s = smtplib.SMTP(domain)
    s.starttls()

    s.putcmd("vrfy", f"wrongaddress@{chatmail_config.mail_domain}")
    result = s.getreply()
    print(result)
    s.putcmd("vrfy", f"echo@{chatmail_config.mail_domain}")
    result2 = s.getreply()
    print(result2)
    assert result[0] == result2[0] == 252
    assert result[1][0:6] == result2[1][0:6] == b"2.0.0 "
    s.putcmd("vrfy", "wrongaddress")
    result = s.getreply()
    print(result)
    s.putcmd("vrfy", "echo")
    result2 = s.getreply()
    print(result2)
    assert result[0] == result2[0] == 252
    assert result[1][0:6] == result2[1][0:6] == b"2.0.0 "
