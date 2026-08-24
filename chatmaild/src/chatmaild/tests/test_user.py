def test_login_timestamp(testaddr, example_config):
    user = example_config.get_user(testaddr)
    user.set_password("someeqkjwelkqwjleqwe")
    user.set_last_login_timestamp(100000)
    assert user.get_last_login_timestamp() == 86400

    user.set_last_login_timestamp(200000)
    assert user.get_last_login_timestamp() == 86400 * 2


def test_get_password_hash_not_set(testaddr, example_config, caplog):
    user = example_config.get_user(testaddr)
    assert not caplog.records
    assert user.get_password_hash() is None
    assert len(caplog.records) == 0

    user.set_password("")
    assert user.get_password_hash() is None
    assert len(caplog.records) == 1


def test_get_password_hash(make_config, tmp_path):
    config = make_config("something.testrun.org")
    user = config.get_user("user1@something.org")
    enc_password = "l1k2j31lk2j3l1k23j123"
    user.set_password(enc_password)
    assert user.get_password_hash() == enc_password


def test_no_mailboxes_dir(testaddr, example_config, tmp_path):
    p = tmp_path.joinpath("a", "mailboxes")
    example_config.mailboxes_dir = p

    user = example_config.get_user(testaddr)
    user.set_password("someeqkjwelkqwjleqwe")
    user.set_last_login_timestamp(100000)
    assert user.get_last_login_timestamp() == 86400


def test_set_get_cleartext_flag(testaddr, example_config, tmp_path):
    p = tmp_path.joinpath("a", "mailboxes")
    example_config.mailboxes_dir = p

    user = example_config.get_user(testaddr)
    user.set_password("someeqkjwelkqwjleqwe")
    user.set_last_login_timestamp(100000)
    assert user.get_last_login_timestamp() == 86400

    assert not user.is_incoming_cleartext_ok()
    user.allow_incoming_cleartext()
    assert user.is_incoming_cleartext_ok()
