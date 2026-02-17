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


def test_create_dclogin_url():
    url = create_dclogin_url("user@example.org", "p@ss w+rd")
    assert url.startswith("dclogin:")
    assert "v=1" in url
    assert "ic=3" in url
    # email @ must be encoded
    assert "user%40example.org" in url
    # password special chars must be encoded
    assert "p%40ss" in url
    assert "w%2Brd" in url


def test_print_new_account(capsys, monkeypatch, maildomain, tmpdir, example_config):
    monkeypatch.setattr(chatmaild.newemail, "CONFIG_PATH", str(example_config._inipath))
    print_new_account()
    out, err = capsys.readouterr()
    lines = out.split("\n")
    assert lines[0] == "Content-Type: application/json"
    assert not lines[1]
    dic = json.loads(lines[2])
    assert dic["email"].endswith(f"@{example_config.mail_domain}")
    assert len(dic["password"]) >= 10
    # default tls_cert=acme should not include dclogin_url
    assert "dclogin_url" not in dic


def test_print_new_account_self_signed(capsys, monkeypatch, make_config):
    config = make_config("chat.example.org", {"tls_cert": "self"})
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
