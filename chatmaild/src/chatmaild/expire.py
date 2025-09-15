"""
Expire old messages and addresses.

"""

import os
import shutil
import sys
from argparse import ArgumentParser
from datetime import datetime
from stat import S_ISREG

from chatmaild.config import read_config


class FileEntry:
    def __init__(self, relpath, mtime, size):
        self.relpath = relpath
        self.mtime = mtime
        self.size = size

    def __hash__(self):
        return hash(self.relpath)

    def __repr__(self):
        return f"<FileEntry size={self.size} '{self.relpath}' >"

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
        self.maxnum = maxnum

    def iter_mailboxes(self, callback=None):
        for name in os.listdir(self.basedir)[: self.maxnum]:
            if "@" in name:
                basedir = joinpath(self.basedir, name)
                mailbox = MailboxStat(basedir)
                if callback is not None:
                    callback(mailbox)


class MailboxStat:
    last_login = None

    def __init__(self, basedir):
        self.basedir = basedir = str(basedir)
        # all detected messages in cur/new/tmp folders
        self.messages = []

        # all detected files in mailbox top dir
        self.extrafiles = []

        # total size of all detected files
        self.totalsize = 0

        # scan all relevant files (without recursion)
        for name in os.listdir(basedir):
            fpath = joinpath(basedir, name)
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


def print_info(msg):
    print(msg, file=sys.stderr)


class Expiry:
    def __init__(self, config, stats, dry, now):
        self.config = config
        self.stats = stats
        self.dry = dry
        self.now = now

    def remove_mailbox(self, mboxdir):
        print_info(f"removing {mboxdir}")
        if not self.dry:
            shutil.rmtree(mboxdir)

    def remove_file(self, path):
        print_info(f"removing {path}")
        if not self.dry:
            try:
                os.unlink(path)
            except FileNotFoundError:
                print_info(f"file not found/vanished {path}")

    def process_mailbox_stat(self, mbox):
        cutoff_without_login = (
            self.now - int(self.config.delete_inactive_users_after) * 86400
        )
        cutoff_mails = self.now - int(self.config.delete_mails_after) * 86400
        cutoff_large_mails = self.now - int(self.config.delete_large_after) * 86400

        changed = False
        if mbox.last_login and mbox.last_login < cutoff_without_login:
            self.remove_mailbox(mbox.basedir)
            return

        os.chdir(mbox.basedir)
        for message in mbox.messages:
            if message.mtime < cutoff_mails:
                self.remove_file(message.relpath)
            elif message.size > 200000 and message.mtime < cutoff_large_mails:
                self.remove_file(message.relpath)
            else:
                continue
            changed = True
        if changed:
            self.remove_file("maildirsize")


def main(args):
    """Expire mailboxes and messages according to chatmail config"""
    parser = ArgumentParser(description=main.__doc__)
    parser.add_argument(
        "chatmail_ini", action="store", help="path pointing to chatmail.ini file"
    )
    parser.add_argument(
        "mailboxes_dir", action="store", help="path to directory of mailboxes"
    )
    parser.add_argument(
        "--days", action="store", help="assume date to be days older than now"
    )

    parser.add_argument(
        "--maxnum",
        default=None,
        action="store",
        help="maximum number of mailbxoes to iterate on",
    )

    parser.add_argument(
        "--remove",
        dest="remove",
        action="store_true",
        help="actually remove all expired files and dirs",
    )
    args = parser.parse_args([str(x) for x in args])

    config = read_config(args.chatmail_ini)
    now = datetime.utcnow().timestamp()
    if args.days:
        now = now - 86400 * int(args.days)

    maxnum = int(args.maxnum) if args.maxnum else None
    stats = Stats(args.mailboxes_dir, maxnum=maxnum)
    exp = Expiry(config, stats, dry=not args.remove, now=now)
    stats.iter_mailboxes(exp.process_mailbox_stat)


if __name__ == "__main__":
    main(sys.argv[1:])
