from unittest.mock import call

from cmdeploy import removers


def test_remove_chatmail_purges_packages_and_state(make_config, monkeypatch):
    config = make_config("chat.example.org")

    apt_calls = []
    file_calls = []
    dir_calls = []
    shell_calls = []
    line_calls = []

    monkeypatch.setattr(removers.apt, "packages", lambda **kw: apt_calls.append(kw))
    monkeypatch.setattr(removers.files, "file", lambda **kw: file_calls.append(kw))
    monkeypatch.setattr(removers.files, "directory", lambda **kw: dir_calls.append(kw))
    monkeypatch.setattr(removers.server, "shell", lambda **kw: shell_calls.append(kw))
    monkeypatch.setattr(removers.files, "line", lambda **kw: line_calls.append(kw))

    removers.remove_chatmail(config._inipath)

    assert apt_calls == [
        {
            "name": "Purge chatmail relay packages",
            "packages": removers.PACKAGE_NAMES,
            "present": False,
            "purge": True,
        }
    ]
    assert call(path="/usr/local/lib/chatmaild", present=False) in [
        call(path=entry["path"], present=entry["present"]) for entry in dir_calls
    ]
    assert call(path=str(config.mailboxes_dir), present=False) in [
        call(path=entry["path"], present=entry["present"]) for entry in dir_calls
    ]
    assert any(entry["path"] == "/var/lib/acme" for entry in dir_calls)
    assert any(
        entry["path"] == "/etc/systemd/system/doveauth.service" for entry in file_calls
    )
    assert any(entry["path"] == "/etc/postfix/main.cf" for entry in file_calls)
    assert any(entry["path"] == "/etc/opendkim.conf" for entry in file_calls)
    assert any(entry["path"] == "/etc/postfix" for entry in dir_calls)
    assert any(entry["path"] == "/var/log/nginx" for entry in dir_calls)
    assert any(
        "userdel -r vmail" in command
        for entry in shell_calls
        for command in entry["commands"]
    )
    assert any(entry["path"] == "/etc/environment" for entry in line_calls)


def test_remove_chatmail_keep_packages_and_external_tls(make_config, monkeypatch):
    config = make_config(
        "chat.example.org",
        {"tls_external_cert_and_key": "/certs/fullchain.pem /certs/privkey.pem"},
    )

    apt_calls = []
    file_calls = []
    dir_calls = []

    monkeypatch.setattr(removers.apt, "packages", lambda **kw: apt_calls.append(kw))
    monkeypatch.setattr(removers.files, "file", lambda **kw: file_calls.append(kw))
    monkeypatch.setattr(removers.files, "directory", lambda **kw: dir_calls.append(kw))
    monkeypatch.setattr(removers.server, "shell", lambda **kw: None)
    monkeypatch.setattr(removers.files, "line", lambda **kw: None)

    removers.remove_chatmail(config._inipath, keep_packages=True)

    assert apt_calls == []
    removed_files = {entry["path"] for entry in file_calls}
    removed_dirs = {entry["path"] for entry in dir_calls}
    assert "/certs/fullchain.pem" not in removed_files
    assert "/certs/privkey.pem" not in removed_files
    assert "/var/lib/acme" not in removed_dirs
    assert "/etc/nginx" not in removed_dirs
    assert "/etc/unbound" not in removed_dirs
    assert "/etc/postfix" not in removed_dirs
    assert "/etc/dovecot" not in removed_dirs
    assert "/etc/nginx/nginx.conf" in removed_files
    assert "/etc/unbound/unbound.conf.d/chatmail.conf" in removed_files


def test_remove_chatmail_removes_self_signed_tls(make_config, monkeypatch):
    config = make_config("_test.example.org")
    file_calls = []

    monkeypatch.setattr(removers.apt, "packages", lambda **kw: None)
    monkeypatch.setattr(removers.files, "file", lambda **kw: file_calls.append(kw))
    monkeypatch.setattr(removers.files, "directory", lambda **kw: None)
    monkeypatch.setattr(removers.server, "shell", lambda **kw: None)
    monkeypatch.setattr(removers.files, "line", lambda **kw: None)

    removers.remove_chatmail(config._inipath)

    removed = {entry["path"] for entry in file_calls}
    assert "/etc/ssl/certs/mailserver.pem" in removed
    assert "/etc/ssl/private/mailserver.key" in removed
