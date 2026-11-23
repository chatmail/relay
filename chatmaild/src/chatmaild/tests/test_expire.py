import itertools
import os
import random
import shutil
import time
from fnmatch import fnmatch
from pathlib import Path

import pytest

from chatmaild.expire import (
    Expiry,
    FileEntry,
    MailboxStat,
    expire_to_target,
    get_file_entry,
    iter_mailboxes,
    os_listdir_if_exists,
    parse_dovecot_filename,
    quota_expire_main,
    scan_mailbox_messages,
)
from chatmaild.expire import daily_expire_main as expiry_main

MB = 1024 * 1024


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
    now = time.time()

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


def test_mbox_without_password(mbox1, example_config, capsys):
    password = Path(mbox1.basedir).joinpath("password")
    os.remove(password)
    mbox_rescan = MailboxStat(mbox1.basedir)
    assert mbox_rescan.last_login is None

    exp = Expiry(example_config, dry=False, now=time.time(), verbose=False)
    exp.process_mailbox_stat(mbox_rescan)
    out, err = capsys.readouterr()
    assert "doesn't have last_login but isn't empty" in err
    assert os.path.isdir(mbox_rescan.basedir)

    for entry in os.scandir(mbox_rescan.basedir):
        if os.path.isdir(entry):
            shutil.rmtree(entry)
        else:
            os.remove(entry)

    exp.process_mailbox_stat(mbox_rescan)
    out, err = capsys.readouterr()
    assert "doesn't have last_login but isn't empty" not in err
    assert not os.path.isdir(mbox_rescan.basedir)


def test_expiry_cli_prom(example_config, mbox1, tmp_path):
    days = int(example_config.delete_mails_after) + 1
    create_new_messages(mbox1.basedir, ["cur/msg_old"], size=1000, days=days)
    path = tmp_path / "expire.prom"
    expiry_main([str(example_config._inipath), "--remove", "--prom", str(path)])
    text = path.read_text()
    # fill_mbox leaves 500 + 600 bytes of messages after msg_old expired
    assert 'chatmail_storage_bytes{kind="messages"} 1100\n' in text
    assert 'chatmail_messages_count{min_size="0"} 2\n' in text
    assert 'chatmail_accounts{kind="all"} 1\n' in text
    # msg_old and maildirsize
    assert "chatmail_expire_removed_files 2\n" in text
    assert "chatmail_expire_last_run_timestamp_seconds " in text


def test_expiry_cli_basic(example_config, mbox1):
    mboxdir = Path(mbox1.basedir)
    p1 = _create_message(mboxdir, "cur", 400 * MB, days_old=2, disk_size=10)
    p2 = _create_message(mboxdir, "cur", 400 * MB, days_old=2, disk_size=10)
    args = (str(example_config._inipath),)
    expiry_main(args)
    assert p1.exists() and p2.exists()
    assert mboxdir.joinpath("maildirsize").exists()


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


# --- quota expire tests ---

_msg_counter = itertools.count(1)


def _create_message(basedir, sub, size, days_old=0, disk_size=None):
    seq = next(_msg_counter)
    mtime = int(time.time() - days_old * 86400)
    name = f"{mtime}.M1P1Q{seq}.hostname,S={size},W={size}:2,S"
    path = basedir / sub / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * (disk_size if disk_size is not None else size))
    os.utime(path, (mtime, mtime))
    return path


def test_parse_dovecot_filename():
    e = parse_dovecot_filename("cur/1775324677.M448978P3029757.exam,S=3235,W=3305:2,S")
    assert e.path == "cur/1775324677.M448978P3029757.exam,S=3235,W=3305:2,S"
    assert e.mtime == 1775324677
    assert e.quota_size == 3235
    assert parse_dovecot_filename("cur/msg_without_structure") is None


def test_expire_to_target(tmp_path):
    _create_message(tmp_path, "cur", MB, days_old=10, disk_size=100)
    _create_message(tmp_path, "new", MB, days_old=5)
    _create_message(tmp_path, "cur", MB, days_old=0)  # undeletable (<1 hour)
    assert len(scan_mailbox_messages(tmp_path)) == 3
    # removes oldest first, uses S= size not disk size
    removed = expire_to_target(tmp_path, MB)
    assert len(removed) == 2
    msgs = scan_mailbox_messages(tmp_path)
    assert len(msgs) == 1
    # the surviving message is the fresh undeletable one
    assert msgs[0].mtime > time.time() - 3600


def test_quota_expire_main(tmp_path, capsys):
    mbox = tmp_path / "user@example.org"
    _create_message(mbox, "cur", 2 * MB, days_old=5)
    (mbox / "maildirsize").write_text("x")
    quota_expire_main([str(1), str(mbox)])
    _, err = capsys.readouterr()
    assert "quota-expire: removed 1 message(s) from user@example.org" in err
    assert not (mbox / "maildirsize").exists()
