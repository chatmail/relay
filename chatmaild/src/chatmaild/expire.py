"""
Expire old messages and addresses.

"""

import os
import shutil
import sys
import time
from argparse import ArgumentParser
from collections import namedtuple
from datetime import datetime
from stat import S_ISREG

from chatmaild.config import read_config

FileEntry = namedtuple("FileEntry", ("relpath", "mtime", "size"))


def iter_mailboxes(basedir, maxnum):
    for name in os.listdir(basedir)[:maxnum]:
        if "@" in name:
            yield MailboxStat(basedir + "/" + name)


class MailboxStat:
    last_login = None

    def __init__(self, basedir):
        self.basedir = str(basedir)
        # all detected messages in cur/new/tmp folders
        self.messages = []

        # all detected files in mailbox top dir
        self.extrafiles = []

        # total size of all detected files
        self.totalsize = 0

        # scan all relevant files (without recursion)
        os.chdir(self.basedir)
        for name in os.listdir("."):
            if name in ("cur", "new", "tmp"):
                for msg_name in os.listdir(name):
                    relpath = name + "/" + msg_name
                    st = os.stat(relpath)
                    self.messages.append(FileEntry(relpath, st.st_mtime, st.st_size))
                    self.totalsize += st.st_size
            else:
                st = os.stat(name)
                if S_ISREG(st.st_mode):
                    self.extrafiles.append(FileEntry(name, st.st_mtime, st.st_size))
                    if name == "password":
                        self.last_login = st.st_mtime
                self.totalsize += st.st_size
        self.extrafiles.sort(key=lambda x: -x.size)


def print_info(msg):
    print(msg, file=sys.stderr)


class Expiry:
    def __init__(self, config, dry, now, verbose):
        self.config = config
        self.dry = dry
        self.now = now
        self.verbose = verbose
        self.del_mboxes = 0
        self.all_mboxes = 0
        self.del_files = 0
        self.all_files = 0
        self.start = time.time()

    def remove_mailbox(self, mboxdir):
        if self.verbose:
            print_info(f"removing {mboxdir}")
        if not self.dry:
            shutil.rmtree(mboxdir)
        self.del_mboxes += 1

    def remove_file(self, path):
        if self.verbose:
            print_info(f"removing {path}")
        if not self.dry:
            try:
                os.unlink(path)
            except FileNotFoundError:
                print_info(f"file not found/vanished {path}")
        self.del_files += 1

    def process_mailbox_stat(self, mbox):
        cutoff_without_login = (
            self.now - int(self.config.delete_inactive_users_after) * 86400
        )
        cutoff_mails = self.now - int(self.config.delete_mails_after) * 86400
        cutoff_large_mails = self.now - int(self.config.delete_large_after) * 86400

        self.all_mboxes += 1
        changed = False
        if mbox.last_login and mbox.last_login < cutoff_without_login:
            self.remove_mailbox(mbox.basedir)
            return

        # all to-be-removed files are relative to the mailbox basedir
        os.chdir(mbox.basedir)
        self.all_files += len(mbox.messages)
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

    def get_summary(self):
        return (
            f"Removed {self.del_mboxes} out of {self.all_mboxes} mailboxes "
            f"and {self.del_files} out of {self.all_files} files "
            f"in {time.time()-self.start:2.2f} seconds"
        )


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
        "-v",
        dest="verbose",
        action="store_true",
        help="print out removed files and mailboxes",
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
    exp = Expiry(config, dry=not args.remove, now=now, verbose=args.verbose)
    for mailbox in iter_mailboxes(os.path.abspath(args.mailboxes_dir), maxnum=maxnum):
        exp.process_mailbox_stat(mailbox)
    print(exp.get_summary())


if __name__ == "__main__":
    main(sys.argv[1:])
