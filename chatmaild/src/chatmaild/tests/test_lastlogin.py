import time

from chatmaild.doveauth import AuthDictProxy
from chatmaild.lastlogin import (
    LastLoginDictProxy,
)


def test_handle_dovecot_request_last_login(testaddr, example_config):
    dictproxy = LastLoginDictProxy(config=example_config)

    authproxy = AuthDictProxy(config=example_config)
    authproxy.lookup_passdb(testaddr, "1l2k3j1l2k3jl123")

    dictproxy_transactions = {}

    # Begin transaction
    tx = "1111"
    msg = f"B{tx}\t{testaddr}"
    res = dictproxy.handle_dovecot_request(msg, dictproxy_transactions)
    assert not res
    assert dictproxy_transactions == {tx: dict(addr=testaddr, res="O\n")}

    # set last-login info for user
    user = dictproxy.config.get_user(testaddr)
    timestamp = int(time.time())
    msg = f"S{tx}\tshared/last-login/{testaddr}\t{timestamp}"
    res = dictproxy.handle_dovecot_request(msg, dictproxy_transactions)
    assert not res
    assert len(dictproxy_transactions) == 1
    read_timestamp = user.get_last_login_timestamp()
    assert read_timestamp == timestamp // 86400 * 86400

    # finish transaction
    msg = f"C{tx}"
    res = dictproxy.handle_dovecot_request(msg, dictproxy_transactions)
    assert res == "O\n"
    assert len(dictproxy_transactions) == 0
