import json

import chatmaild
from chatmaild.newemail import (
    create_dclogin_url,
    create_newemail_dict,
    print_new_account,
)


def test_create_newemail_dict(example_config):
    ac1 = create_newemail_dict(example_config)
    assert "@" in ac1["email"]
    assert len(ac1["password"]) >= 10

    ac2 = create_newemail_dict(example_config)

    assert ac1["email"] != ac2["email"]
    assert ac1["password"] != ac2["password"]


def test_create_newemail_dict_ip(ipv4_config):
    ac = create_newemail_dict(ipv4_config)
    assert ac["email"].endswith("@[1.3.3.7]")


def test_create_dclogin_url(example_config):
    addr = "user@example.org"
    password = "p@ss w+rd"
    url = create_dclogin_url(example_config, addr, password)
    assert url.startswith("dclogin:")
    assert "v=1" in url
    assert "ic=3" in url

    assert addr in url
    # password special chars must be encoded
    assert "p%40ss" in url
    assert "w%2Brd" in url


def test_create_dclogin_url_ipv4(ipv4_config):
    addr = "user@[1.3.3.7]"
    password = "p@ss w+rd"
    url = create_dclogin_url(ipv4_config, addr, password)
    assert url.startswith("dclogin:")
    assert "v=1" in url
    assert "ic=3" in url
    assert addr in url


def test_print_new_account(capsys, monkeypatch, maildomain, tmpdir, example_config):
    monkeypatch.setattr(chatmaild.newemail, "CONFIG_PATH", str(example_config._inipath))
    print_new_account()
    out, err = capsys.readouterr()
    lines = out.split("\n")
    assert lines[0] == "Content-Type: application/json"
    assert not lines[1]
    dic = json.loads(lines[2])
    assert dic["email"].endswith(f"@{example_config.mail_domain_deliverable}")
    assert len(dic["password"]) >= 10
    # default tls_cert=acme should not include dclogin_url
    assert "dclogin_url" not in dic


def test_print_new_account_self_signed(capsys, monkeypatch, make_config):
    config = make_config("_test.example.org")
    monkeypatch.setattr(chatmaild.newemail, "CONFIG_PATH", str(config._inipath))
    print_new_account()
    out, err = capsys.readouterr()
    lines = out.split("\n")
    dic = json.loads(lines[2])
    assert "dclogin_url" in dic
    url = dic["dclogin_url"]
    assert url.startswith("dclogin:")
    assert "ic=3" in url

    assert dic["email"].split("@")[0] in url
