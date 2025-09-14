import random
from datetime import datetime
from pathlib import Path

import pytest

from chatmaild.expire import FileEntry, MailboxStat
from chatmaild.expire import main as expiry_main
from chatmaild.fsreport import Report, Stats

# XXX maildirsize (used by dovecot quota) needs to be removed after removing files


@pytest.fixture
def mailboxdir1(tmp_path):
    mailboxdir1 = tmp_path.joinpath("mailbox1@example.org")
    mailboxdir1.mkdir()
    password = mailboxdir1.joinpath("password")
    password.write_text("xxx")

    garbagedir = mailboxdir1.joinpath("garbagedir")
    garbagedir.mkdir()

    cur = mailboxdir1.joinpath("cur")
    new = mailboxdir1.joinpath("new")
    cur.mkdir()
    msg_cur = cur.joinpath("msg1")
    msg_cur.write_text("xxx")
    new.mkdir()
    msg_new = new.joinpath("msg2")
    msg_new.write_text("xxx123")
    return mailboxdir1


@pytest.fixture
def mbox1(mailboxdir1):
    return MailboxStat(mailboxdir1)


def test_filentry_ordering():
    l = [FileEntry(f"x{i}", size=i + 10, mtime=1000 - i) for i in range(10)]
    sorted = list(l)
    random.shuffle(l)
    l.sort(key=lambda x: x.size)
    assert l == sorted


def test_stats_mailbox(mbox1):
    password = Path(mbox1.mailboxdir).joinpath("password")
    assert mbox1.last_login == password.stat().st_mtime
    assert len(mbox1.messages) == 2

    msgs = list(mbox1.messages)
    assert len(msgs) == 2
    assert msgs[0].size == 3  # cur
    assert msgs[1].size == 6  # new

    extra = Path(mbox1.mailboxdir).joinpath("large-extra")
    extra.write_text("x" * 1000)
    Path(mbox1.mailboxdir).joinpath("index-something").write_text("123")
    mbox2 = MailboxStat(mbox1.mailboxdir)
    assert len(mbox2.extrafiles) == 3
    assert mbox2.extrafiles[0].size == 1000

    # cope well with mailbox dirs that have no password (for whatever reason)
    Path(mbox1.mailboxdir).joinpath("password").unlink()
    mbox3 = MailboxStat(mbox1.mailboxdir)
    assert mbox3.last_login is None


def test_report(mbox1):
    now = datetime.utcnow().timestamp()
    mailboxes_dir = Path(mbox1.mailboxdir).parent
    stats = Stats(str(mailboxes_dir), maxnum=None)
    rep = Report(stats, now=now)
    stats.iter_mailboxes(rep.process_mailbox_stat)
    rep.dump_summary()


def test_expiry(example_config, mbox1):
    args = example_config._inipath, mbox1.mailboxdir, 10000
    expiry_main(args)
