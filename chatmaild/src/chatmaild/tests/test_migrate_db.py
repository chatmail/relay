import sqlite3

from chatmaild.migrate_db import migrate_from_db_to_maildir


def test_migration_not_exists(tmp_path, example_config):
    example_config.passdb_path = tmp_path.joinpath("sqlite")


def test_migration(tmp_path, example_config, caplog):
    passdb_path = tmp_path.joinpath("passdb.sqlite")
    uri = f"file:{passdb_path}?mode=rwc"
    sqlconn = sqlite3.connect(uri, timeout=60, uri=True)
    sqlconn.execute(
        """
        CREATE TABLE users (
            addr TEXT PRIMARY KEY,
            password TEXT,
            last_login INTEGER
        )
    """
    )
    all = {}

    for i in range(500):
        values = (f"somsom{i:03}@example.org", f"passwo{i:03}", i * 86400)
        sqlconn.execute(
            """
            INSERT INTO users (addr, password, last_login)
            VALUES (?, ?, ?)""",
            values,
        )
        all[values[0]] = values[1:]

    for i in range(500):
        values = (f"pompom{i:03}@example.org", f"wopass{i:03}", "")
        sqlconn.execute(
            """
            INSERT INTO users (addr, password, last_login)
            VALUES (?, ?, ?)""",
            values,
        )
        all[values[0]] = values[1:]

    sqlconn.commit()
    sqlconn.close()

    assert passdb_path.stat().st_size > 10000

    example_config.passdb_path = passdb_path
    # ensure logging.info records are captured regardless of global configuration
    caplog.set_level("INFO")

    assert not caplog.records

    migrate_from_db_to_maildir(example_config, chunking=500)
    assert len(caplog.records) > 3

    for path in example_config.mailboxes_dir.iterdir():
        if "@" not in path.name:
            continue
        password, last_login = all.pop(path.name)
        user = example_config.get_user(path.name)
        if last_login:
            assert user.get_last_login_timestamp() == last_login
        assert password == user.get_userdb_dict()["password"]

    assert not all
    assert not example_config.passdb_path.exists()
