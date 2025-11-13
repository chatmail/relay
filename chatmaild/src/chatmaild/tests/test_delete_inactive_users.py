import time

from chatmaild.doveauth import AuthDictProxy
from chatmaild.expire import main as main_expire


def test_login_timestamps(example_config):
    testaddr = "someuser@chat.example.org"
    user = example_config.get_user(testaddr)

    # password file needs to be set because it's mtime tracks last-login time
    user.set_password("1l2k3j1l2k3j123")
    for i in range(10):
        user.set_last_login_timestamp(86400 * 4 + i)
        assert user.get_last_login_timestamp() == 86400 * 4


def test_delete_inactive_users(example_config):
    new = time.time()
    old = new - (example_config.delete_inactive_users_after * 86400) - 1
    dictproxy = AuthDictProxy(example_config)

    def create_user(addr, last_login):
        dictproxy.lookup_passdb(addr, "q9mr3faue")
        user = example_config.get_user(addr)
        user.maildir.joinpath("cur").mkdir()
        user.maildir.joinpath("cur", "something").mkdir()
        user.set_last_login_timestamp(timestamp=last_login)

    # create some stale and some new accounts
    to_remove = []
    for i in range(150):
        addr = f"oldold{i:03}@chat.example.org"
        create_user(addr, last_login=old)
        to_remove.append(addr)

    remain = []
    for i in range(5):
        addr = f"newnew{i:03}@chat.example.org"
        create_user(addr, last_login=new)
        remain.append(addr)

    # check pre and post-conditions for delete_inactive_users()

    for addr in to_remove:
        assert example_config.get_user(addr).maildir.exists()

    main_expire(
        args=[
            "--remove",
            str(example_config._inipath),
        ]
    )

    for p in example_config.mailboxes_dir.iterdir():
        assert not p.name.startswith("old")

    for addr in to_remove:
        assert not example_config.get_user(addr).maildir.exists()

    for addr in remain:
        userdir = example_config.get_user(addr).maildir
        assert userdir.exists()
        assert userdir.joinpath("password").read_text()
