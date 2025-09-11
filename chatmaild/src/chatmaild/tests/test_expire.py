import random

from chatmaild.expire import FileEntry, MailboxStat


def test_filentry_ordering():
    l = [FileEntry(f"x{i}", size=i + 10, mtime=1000 - i) for i in range(10)]
    sorted = list(l)
    random.shuffle(l)
    l.sort(key=lambda x: x.size)
    assert l == sorted


def test_stats_mailbox(tmp_path):
    mailboxdir = tmp_path
    password = mailboxdir.joinpath("password")
    password.write_text("xxx")

    garbagedir = mailboxdir.joinpath("garbagedir")
    garbagedir.mkdir()

    cur = mailboxdir.joinpath("cur")
    new = mailboxdir.joinpath("new")
    cur.mkdir()
    msg_cur = cur.joinpath("msg1")
    msg_cur.write_text("xxx")
    new.mkdir()
    msg_new = new.joinpath("msg2")
    msg_new.write_text("xxx123")

    mbox = MailboxStat(tmp_path)
    assert mbox.last_login == password.stat().st_mtime
    assert len(mbox.messages) == 2

    msgs = list(mbox.messages)
    assert len(msgs) == 2
    assert msgs[0].size == 3  # cur

    assert msgs[1].size == 6  # new

    extra = mailboxdir.joinpath("large")
    extra.write_text("x" * 1000)
    mailboxdir.joinpath("index-something").write_text("123")
    mbox = MailboxStat(tmp_path)
    assert len(mbox.extrafiles) == 3
    assert mbox.extrafiles[0].size == 1000
