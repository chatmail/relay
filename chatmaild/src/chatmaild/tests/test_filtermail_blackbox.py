import smtplib
import subprocess
import sys

import pytest


@pytest.fixture
def smtpserver():
    from pytest_localserver import smtp

    server = smtp.Server("127.0.0.1")
    server.start()
    yield server
    server.stop()


@pytest.fixture
def make_popen(request):
    def popen(cmdargs, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw):
        p = subprocess.Popen(
            cmdargs,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        def fin():
            p.terminate()
            out, err = p.communicate()
            print(out.decode("ascii"))
            print(err.decode("ascii"), file=sys.stderr)

        request.addfinalizer(fin)
        return p

    return popen


@pytest.mark.parametrize("filtermail_mode", ["outgoing", "incoming"])
def test_one_mail(
    make_config, make_popen, smtpserver, maildata, filtermail_mode, monkeypatch
):
    monkeypatch.setenv("PYTHONUNBUFFERED", "1")
    smtp_inject_port = 20025
    if filtermail_mode == "outgoing":
        settings = dict(
            postfix_reinject_port=smtpserver.port,
            filtermail_smtp_port=smtp_inject_port,
        )
    else:
        settings = dict(
            postfix_reinject_port_incoming=smtpserver.port,
            filtermail_smtp_port_incoming=smtp_inject_port,
        )

    config = make_config("example.org", settings=settings)
    path = str(config._inipath)

    popen = make_popen(["filtermail", path, filtermail_mode])
    line = popen.stderr.readline().strip()
    if b"loop" not in line:
        print(line.decode("ascii"), file=sys.stderr)
        pytest.fail("starting filtermail failed")

    addr = f"user1@{config.mail_domain}"
    config.get_user(addr).set_password("l1k2j3l1k2j3l")

    # send encrypted mail
    data = str(maildata("encrypted.eml", from_addr=addr, to_addr=addr))
    client = smtplib.SMTP("localhost", smtp_inject_port)
    client.sendmail(addr, [addr], data)
    assert len(smtpserver.outbox) == 1

    # send un-encrypted mail that errors
    data = str(maildata("fake-encrypted.eml", from_addr=addr, to_addr=addr))
    with pytest.raises(smtplib.SMTPDataError) as e:
        client.sendmail(addr, [addr], data)
    assert e.value.smtp_code == 523
