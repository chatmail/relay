from chatmaild.expire import MailboxStat


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

    seen = mbox.get_messages("cur")
    assert len(seen) == 1
    assert seen[0].size == 3

    new = mbox.get_messages("new")
    assert len(new) == 1
    assert new[0].size == 6

    extra = mailboxdir.joinpath("large")
    extra.write_text("x" * 1000)
    mailboxdir.joinpath("index-something").write_text("123")
    mbox = MailboxStat(tmp_path)
    extrafiles = mbox.get_extra_files()
    assert len(extrafiles) == 3
    assert extrafiles[0].size == 1000
