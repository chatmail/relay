"""
Expire old messages and addresses.

"""

import os
import shutil
import sys
from datetime import datetime
from stat import S_ISREG

from chatmaild.config import read_config

# XXX maildirsize (used by dovecot quota) needs to be removed after removing files


class FileEntry:
    def __init__(self, relpath, mtime, size):
        self.relpath = relpath
        self.mtime = mtime
        self.size = size

    def __repr__(self):
        return f"<FileEntry size={self.size} '{self.relpath}'>"

    def fmt_size(self):
        return f"{int(self.size/1000):5.0f}K"

    def fmt_since(self, now):
        diff_seconds = int(now) - int(self.mtime)
        return f"{int(diff_seconds / 86400):2.0f}d"

    def __eq__(self, other):
        return (
            self.relpath == other.relpath
            and self.size == other.size
            and self.mtime == other.mtime
        )


def joinpath(name, extra):
    return name + "/" + extra


class Stats:
    def __init__(self, basedir, maxnum=None):
        self.basedir = str(basedir)
        self.mailboxes = []
        self.maxnum = maxnum

    def iter_mailboxes(self):
        for mailbox in os.listdir(self.basedir)[: self.maxnum]:
            if "@" in mailbox:
                mailboxdir = joinpath(self.basedir, mailbox)
                self.mailboxes.append(MailboxStat(mailboxdir))


class MailboxStat:
    def __init__(self, mailboxdir):
        self.mailboxdir = mailboxdir = str(mailboxdir)
        # all detected messages in cur/new/tmp folders
        self.messages = []

        # all detected files in mailbox top dir
        self.extrafiles = []

        # total size of all detected files
        self.totalsize = 0

        # scan all relevant files (without recursion)
        for name in os.listdir(mailboxdir):
            fpath = joinpath(mailboxdir, name)
            if name in ("cur", "new", "tmp"):
                for msg_name in os.listdir(fpath):
                    msg_path = joinpath(fpath, msg_name)
                    st = os.stat(msg_path)
                    relpath = joinpath(name, msg_name)
                    self.messages.append(
                        FileEntry(relpath, mtime=st.st_mtime, size=st.st_size)
                    )
                    self.totalsize += st.st_size
            else:
                st = os.stat(fpath)
                if S_ISREG(st.st_mode):
                    self.extrafiles.append(FileEntry(name, st.st_mtime, st.st_size))
                self.totalsize += st.st_size
        self.extrafiles.sort(key=lambda x: -x.size)

    @property
    def last_login(self):
        for entry in self.extrafiles:
            if entry.relpath == "password":
                return entry.mtime


def run_expire(config, basedir, now, dry=True, maxnum=None):
    stat = Stats(basedir, maxnum=maxnum)
    stat.iter_mailboxes()
    cutoff_date_without_login = now - int(config.delete_inactive_users_after) * 86400
    cutoff_date_mails = now - int(config.delete_mails_after) * 86400
    cutoff_date_large_mails = now - int(config.delete_large_after) * 86400

    def rmtree(path):
        if dry:
            print("would remove mailbox", path)
        else:
            shutil.rmtree(path, ignore_errors=True)

    def unlink(mailboxdir, message):
        if dry:
            relpath = os.path.basename(mailboxdir) + message.relpath
            print(
                f"would remove {message.fmt_since(now)} {message.fmt_size()} {relpath}"
            )
        else:
            os.unlink(path)

    for mbox in stat.mailboxes:
        changed = False
        if mbox.last_login and mbox.last_login < cutoff_date_without_login:
            rmtree(mbox.mailboxdir)
            continue
        for message in mbox.messages:
            path = joinpath(mbox.mailboxdir, message.relpath)
            if message.mtime < cutoff_date_mails:
                unlink(mbox.mailboxdir, message)
            elif message.size > 200000 and message.mtime < cutoff_date_large_mails:
                unlink(mbox.mailboxdir, message)
            else:
                continue
            changed = True
        if changed and not dry:
            p = joinpath(mbox.mailboxdir, "maildirsize")
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass


def main():
    cfgpath, basedir, maxnum = sys.argv[1:]
    config = read_config(cfgpath)
    now = datetime.utcnow().timestamp()
    now = datetime(2025, 9, 9).timestamp()
    run_expire(config, basedir, maxnum=int(maxnum), now=now)


if __name__ == "__main__":
    main()
