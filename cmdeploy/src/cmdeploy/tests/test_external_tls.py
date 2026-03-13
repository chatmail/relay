"""Functional tests for tls_external_cert_and_key option."""

import json

import chatmaild.newemail
import pytest
from chatmaild.config import read_config, write_initial_config


def make_external_config(tmp_path, cert_key=None):
    inipath = tmp_path / "chatmail.ini"
    overrides = {}
    if cert_key is not None:
        overrides["tls_external_cert_and_key"] = cert_key
    write_initial_config(inipath, "chat.example.org", overrides=overrides)
    return inipath


def test_external_tls_config_reads_paths(tmp_path):
    inipath = make_external_config(
        tmp_path,
        cert_key=(
            "/etc/letsencrypt/live/chat.example.org/fullchain.pem"
            " /etc/letsencrypt/live/chat.example.org/privkey.pem"
        ),
    )
    config = read_config(inipath)
    assert config.tls_cert_mode == "external"
    assert (
        config.tls_cert_path == "/etc/letsencrypt/live/chat.example.org/fullchain.pem"
    )
    assert config.tls_key_path == "/etc/letsencrypt/live/chat.example.org/privkey.pem"


def test_external_tls_missing_option_uses_acme(tmp_path):
    config = read_config(make_external_config(tmp_path))
    assert config.tls_cert_mode == "acme"


def test_external_tls_bad_format_raises(tmp_path):
    inipath = make_external_config(tmp_path, cert_key="/only/one/path.pem")
    with pytest.raises(ValueError, match="two space-separated"):
        read_config(inipath)


def test_external_tls_three_paths_raises(tmp_path):
    inipath = make_external_config(tmp_path, cert_key="/a /b /c")
    with pytest.raises(ValueError, match="two space-separated"):
        read_config(inipath)


def test_external_tls_no_dclogin_url(tmp_path, capsys, monkeypatch):
    inipath = make_external_config(
        tmp_path, cert_key="/certs/fullchain.pem /certs/privkey.pem"
    )
    monkeypatch.setattr(chatmaild.newemail, "CONFIG_PATH", str(inipath))
    chatmaild.newemail.print_new_account()
    out, _ = capsys.readouterr()
    lines = out.split("\n")
    dic = json.loads(lines[2])
    assert "dclogin_url" not in dic


def test_external_tls_selects_correct_deployer(tmp_path):
    from cmdeploy.tls.deployer import (
        AcmetoolDeployer,
        ExternalTlsDeployer,
        SelfSignedTlsDeployer,
        get_tls_deployers,
    )

    inipath = make_external_config(
        tmp_path, cert_key="/certs/fullchain.pem /certs/privkey.pem"
    )
    config = read_config(inipath)
    deployers = get_tls_deployers(config, "chat.example.org")

    # all deployers are present, but only ExternalTlsDeployer is enabled
    external_deployer = [d for d in deployers if isinstance(d, ExternalTlsDeployer)][0]
    selfsigned_deployer = [
        d for d in deployers if isinstance(d, SelfSignedTlsDeployer)
    ][0]
    acme_deployer = [d for d in deployers if isinstance(d, AcmetoolDeployer)][0]

    assert external_deployer.enabled
    assert not selfsigned_deployer.enabled
    assert not acme_deployer.enabled

    assert external_deployer.cert_path == "/certs/fullchain.pem"
    assert external_deployer.key_path == "/certs/privkey.pem"
