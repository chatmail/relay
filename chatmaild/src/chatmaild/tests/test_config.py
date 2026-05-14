import pytest

from chatmaild.config import (
    is_valid_ipv4,
    parse_size_mb,
    read_config,
)


def test_read_config_basic(example_config):
    assert example_config.mail_domain == "chat.example.org"
    assert not example_config.privacy_supervisor and not example_config.privacy_mail
    assert not example_config.privacy_pdo and not example_config.privacy_postal

    inipath = example_config._inipath
    inipath.write_text(
        inipath.read_text().replace(
            "#max_user_send_per_minute = 60",
            "max_user_send_per_minute = 37",
        )
    )
    example_config = read_config(inipath)
    assert example_config.max_user_send_per_minute == 37
    assert example_config.mail_domain == "chat.example.org"
    assert example_config.ipv4_relay is None


def test_read_config_ipv4(ipv4_config):
    assert ipv4_config.ipv4_relay == "1.3.3.7"
    assert ipv4_config.mail_domain == "[1.3.3.7]"


def test_read_config_basic_using_defaults(tmp_path, maildomain):
    inipath = tmp_path.joinpath("chatmail.ini")
    inipath.write_text(f"[params]\nmail_domain = {maildomain}")
    example_config = read_config(inipath)
    assert example_config.max_user_send_per_minute == 60
    assert example_config.filtermail_smtp_port_incoming == 10081
    assert example_config.filtermail_smtp_port == 10080
    assert example_config.postfix_reinject_port == 10025
    assert example_config.max_user_send_per_minute == 60
    assert example_config.max_mailbox_size == "500M"
    assert example_config.delete_mails_after == "20"
    assert example_config.delete_large_after == "7"
    assert example_config.username_min_length == 9
    assert example_config.username_max_length == 9
    assert example_config.password_min_length == 9
    assert example_config.unused_keys == []


def test_config_unused_keys(make_config):
    config = make_config("chat.example.org", {"passthrough_senders": "x@y.org"})
    assert config.unused_keys == ["passthrough_senders"]


def test_config_userstate_paths(make_config, tmp_path):
    config = make_config("something.testrun.org")
    mailboxes_dir = config.mailboxes_dir
    passdb_path = config.passdb_path
    assert mailboxes_dir.name == "something.testrun.org"
    assert str(passdb_path) == "/home/vmail/passdb.sqlite"
    assert config.mail_domain == "something.testrun.org"
    path = config.get_user("user1@something.testrun.org").maildir
    assert not path.exists()
    assert path == mailboxes_dir.joinpath("user1@something.testrun.org")

    with pytest.raises(ValueError):
        config.get_user("")

    with pytest.raises(ValueError):
        config.get_user(None)

    with pytest.raises(ValueError):
        config.get_user("../some@something.testrun.org").maildir

    with pytest.raises(ValueError):
        config.get_user("..").maildir

    with pytest.raises(ValueError):
        config.get_user(".")


def test_config_max_message_size(make_config, tmp_path):
    config = make_config("something.testrun.org", dict(max_message_size="10000"))
    assert config.max_message_size == 10000


def test_config_tls_default_acme(make_config):
    config = make_config("chat.example.org")
    assert config.tls_cert_mode == "acme"
    assert config.tls_cert_path == "/var/lib/acme/live/chat.example.org/fullchain"
    assert config.tls_key_path == "/var/lib/acme/live/chat.example.org/privkey"


def test_config_tls_self(make_config):
    config = make_config("_test.example.org")
    assert config.tls_cert_mode == "self"
    assert config.tls_cert_path == "/etc/ssl/certs/mailserver.pem"
    assert config.tls_key_path == "/etc/ssl/private/mailserver.key"


def test_config_tls_external(make_config):
    config = make_config(
        "chat.example.org",
        {
            "tls_external_cert_and_key": "/custom/fullchain.pem /custom/privkey.pem",
        },
    )
    assert config.tls_cert_mode == "external"
    assert config.tls_cert_path == "/custom/fullchain.pem"
    assert config.tls_key_path == "/custom/privkey.pem"


def test_config_tls_external_overrides_underscore(make_config):
    config = make_config(
        "_test.example.org",
        {
            "tls_external_cert_and_key": "/certs/fullchain.pem /certs/privkey.pem",
        },
    )
    assert config.tls_cert_mode == "external"
    assert config.tls_cert_path == "/certs/fullchain.pem"
    assert config.tls_key_path == "/certs/privkey.pem"


def test_config_tls_external_bad_format(make_config):
    with pytest.raises(ValueError, match="two space-separated"):
        make_config(
            "chat.example.org",
            {
                "tls_external_cert_and_key": "/only/one/path.pem",
            },
        )


def test_parse_size_mb():
    assert parse_size_mb("500M") == 500
    assert parse_size_mb("2G") == 2048
    assert parse_size_mb("  1g  ") == 1024
    assert parse_size_mb("100MB") == 100
    assert parse_size_mb("256") == 256


def test_max_mailbox_size_mb(make_config):
    config = make_config("chat.example.org")
    assert config.max_mailbox_size == "500M"
    assert config.max_mailbox_size_mb == 500


@pytest.mark.parametrize(
    ["input", "result"],
    [
        ("example.org", False),
        ("1.3.3.7", True),
        ("fe::1", False),
        ("ad.1e.dag.adf", False),
        ("12394142", False),
    ],
)
def test_is_valid_ipv4(input, result):
    assert result == is_valid_ipv4(input)
