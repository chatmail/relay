import os
import random
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path

import pytest

from chatmaild.expire import (
    FileEntry,
    MailboxStat,
    get_file_entry,
    iter_mailboxes,
    os_listdir_if_exists,
)
from chatmaild.expire import main as expiry_main
from chatmaild.fsreport import main as report_main


def fill_mbox(folderdir):
    password = folderdir.joinpath("password")
    password.write_text("xxx")
    folderdir.joinpath("maildirsize").write_text("xxx")

    garbagedir = folderdir.joinpath("garbagedir")
    garbagedir.mkdir()
    garbagedir.joinpath("bimbum").write_text("hello")

    create_new_messages(folderdir, ["cur/msg1"], size=500)
    create_new_messages(folderdir, ["new/msg2"], size=600)


def create_new_messages(basedir, relpaths, size=1000, days=0):
    now = datetime.utcnow().timestamp()

    for relpath in relpaths:
        msg_path = Path(basedir).joinpath(relpath)
        msg_path.parent.mkdir(parents=True, exist_ok=True)
        msg_path.write_text("x" * size)
        # accessed now, modified N days ago
        os.utime(msg_path, (now, now - days * 86400))


@pytest.fixture
def mbox1(example_config):
    mboxdir = example_config.mailboxes_dir.joinpath("mailbox1@example.org")
    mboxdir.mkdir()
    fill_mbox(mboxdir)
    return MailboxStat(mboxdir)


def test_deltachat_folder(example_config):
    """Test old setups that might have a .DeltaChat folder where messages also need to get removed."""
    mboxdir = example_config.mailboxes_dir.joinpath("mailbox1@example.org")
    mboxdir.mkdir()
    mbox2dir = mboxdir.joinpath(".DeltaChat")
    mbox2dir.mkdir()
    fill_mbox(mbox2dir)
    mb = MailboxStat(mboxdir)
    assert len(mb.messages) == 2


def test_filentry_ordering(tmp_path):
    l = [FileEntry(f"x{i}", size=i + 10, mtime=1000 - i) for i in range(10)]
    sorted = list(l)
    random.shuffle(l)
    l.sort(key=lambda x: x.size)
    assert l == sorted


def test_no_mailbxoes(tmp_path, capsys):
    assert [] == list(iter_mailboxes(str(tmp_path.joinpath("notexists")), maxnum=10))
    out, err = capsys.readouterr()
    assert "no mailboxes" in err


def test_stats_mailbox(mbox1):
    password = Path(mbox1.basedir).joinpath("password")
    assert mbox1.last_login == password.stat().st_mtime
    assert len(mbox1.messages) == 2

    msgs = list(sorted(mbox1.messages, key=lambda x: x.size))
    assert len(msgs) == 2
    assert msgs[0].size == 500  # cur
    assert msgs[1].size == 600  # new

    create_new_messages(mbox1.basedir, ["large-extra"], size=1000)
    create_new_messages(mbox1.basedir, ["index-something"], size=3)
    mbox2 = MailboxStat(mbox1.basedir)
    assert len(mbox2.extrafiles) == 5
    assert mbox2.extrafiles[0].size == 1000

    # cope well with mailbox dirs that have no password (for whatever reason)
    Path(mbox1.basedir).joinpath("password").unlink()
    mbox3 = MailboxStat(mbox1.basedir)
    assert mbox3.last_login is None


def test_report_no_mailboxes(example_config):
    args = (str(example_config._inipath),)
    report_main(args)


def test_report(mbox1, example_config):
    args = (str(example_config._inipath),)
    report_main(args)
    args = list(args) + "--days 1".split()
    report_main(args)
    args = list(args) + "--min-login-age 1".split()
    report_main(args)
    args = list(args) + "--mdir cur".split()
    report_main(args)


def test_expiry_cli_basic(example_config, mbox1):
    args = (str(example_config._inipath),)
    expiry_main(args)


def test_expiry_cli_old_files(capsys, example_config, mbox1):
    relpaths_old = ["cur/msg_old1", "cur/msg_old1"]
    cutoff_days = int(example_config.delete_mails_after) + 1
    create_new_messages(mbox1.basedir, relpaths_old, size=1000, days=cutoff_days)

    relpaths_large = ["cur/msg_old_large1", "new/msg_old_large2"]
    cutoff_days = int(example_config.delete_large_after) + 1
    create_new_messages(
        mbox1.basedir, relpaths_large, size=1000 * 300, days=cutoff_days
    )

    create_new_messages(mbox1.basedir, ["cur/shouldstay"], size=1000 * 300, days=1)

    args = str(example_config._inipath), "--remove", "-v"
    expiry_main(args)
    out, err = capsys.readouterr()

    allpaths = relpaths_old + relpaths_large + ["maildirsize"]
    for path in allpaths:
        for line in err.split("\n"):
            if fnmatch(line, f"removing*{path}"):
                break
        else:
            if path != "new/msg_old_large2":
                pytest.fail(f"failed to remove {path}\n{err}")

    assert "shouldstay" not in err


def test_get_file_entry(tmp_path):
    assert get_file_entry(str(tmp_path.joinpath("123123"))) is None
    p = tmp_path.joinpath("x")
    p.write_text("hello")
    entry = get_file_entry(str(p))
    assert entry.size == 5
    assert entry.mtime


def test_os_listdir_if_exists(tmp_path):
    tmp_path.joinpath("x").write_text("hello")
    assert len(os_listdir_if_exists(str(tmp_path))) == 1
    assert len(os_listdir_if_exists(str(tmp_path.joinpath("123123")))) == 0
