"""
Expire old messages and addresses.

"""

import os
import shutil
import sys
from datetime import datetime
from stat import S_ISREG

from chatmaild.config import read_config


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

    def iter_mailboxes(self, callback=None):
        for name in os.listdir(self.basedir)[: self.maxnum]:
            if "@" in name:
                mailboxdir = joinpath(self.basedir, name)
                mailbox = MailboxStat(mailboxdir)
                self.mailboxes.append(mailbox)
                if callback is not None:
                    callback(mailbox)


class MailboxStat:
    last_login = None

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
                    if name == "password":
                        self.last_login = st.st_mtime
                self.totalsize += st.st_size
        self.extrafiles.sort(key=lambda x: -x.size)


class Expiry:
    def __init__(self, config, stat, dry, now):
        self.config = config
        self.dry = dry
        self.now = now

    def rmtree(self, path):
        if not self.dry:
            print("would remove mailbox", path)
        else:
            shutil.rmtree(path, ignore_errors=True)

    def unlink(self, mailboxdir, relpath):
        path = joinpath(mailboxdir, relpath)
        if not self.dry:
            for message in self.messages:
                if relpath == message.relpath:
                    print(
                        f"would remove {message.fmt_since(self.now)} {message.fmt_size()} {path}"
                    )
                    break
        else:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass  # it's gone already, fine

    def process_mailbox_stat(self, mbox):
        cutoff_without_login = (
            self.now - int(self.config.delete_inactive_users_after) * 86400
        )
        cutoff_mails = self.now - int(self.config.delete_mails_after) * 86400
        cutoff_large_mails = self.now - int(self.config.delete_large_after) * 86400

        changed = False
        if mbox.last_login and mbox.last_login < cutoff_without_login:
            self.rmtree(mbox.mailboxdir)
            return

        for message in mbox.messages:
            if message.mtime < cutoff_mails:
                self.unlink(mbox.mailboxdir, message.relpath)
            elif message.size > 200000 and message.mtime < cutoff_large_mails:
                self.unlink(mbox.mailboxdir, message.relpath)
            else:
                continue
            changed = True
        if changed:
            self.unlink(mbox.mailboxdir, "maildirsize")


def main(args=None):
    if args is None:
        args = sys.argv[1:]
    else:
        args = list(map(str, args))
    cfgpath, basedir, maxnum = args
    config = read_config(cfgpath)
    now = datetime.utcnow().timestamp()
    now = datetime(2025, 9, 9).timestamp()

    stat = Stats(basedir, maxnum=int(maxnum))
    exp = Expiry(config, stat, dry=True, now=now)
    stat.iter_mailboxes(exp.process_mailbox_stat)


if __name__ == "__main__":
    main()
