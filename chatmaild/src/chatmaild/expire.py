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
    if not os.path.exists(basedir):
        print_info(f"no mailboxes found at: {basedir}")
        return

    for name in os_listdir_if_exists(basedir)[:maxnum]:
        if "@" in name:
            yield MailboxStat(basedir + "/" + name)


def get_file_entry(path):
    """return a FileEntry or None if the path does not exist or is not a regular file."""
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return None
    if not S_ISREG(st.st_mode):
        return None
    return FileEntry(path, st.st_mtime, st.st_size)


def os_listdir_if_exists(path):
    """return a list of names obtained from os.listdir or an empty list if the path does not exist."""
    try:
        return os.listdir(path)
    except FileNotFoundError:
        return []


class MailboxStat:
    last_login = None

    def __init__(self, basedir):
        self.basedir = str(basedir)
        # all detected messages in cur/new/tmp folders
        self.messages = []

        # all detected files in mailbox top dir
        self.extrafiles = []

        # scan all relevant files (without recursion)
        old_cwd = os.getcwd()
        try:
            os.chdir(self.basedir)
        except FileNotFoundError:
            return
        for name in os_listdir_if_exists("."):
            if name in ("cur", "new", "tmp"):
                for msg_name in os_listdir_if_exists(name):
                    entry = get_file_entry(f"{name}/{msg_name}")
                    if entry is not None:
                        self.messages.append(entry)

            else:
                entry = get_file_entry(name)
                if entry is not None:
                    self.extrafiles.append(entry)
                    if name == "password":
                        self.last_login = entry.mtime
        self.extrafiles.sort(key=lambda x: -x.size)
        os.chdir(old_cwd)


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

    def remove_file(self, path, mtime=None):
        if self.verbose:
            if mtime is not None:
                date = datetime.fromtimestamp(mtime).strftime("%b %d")
                print_info(f"removing {date} {path}")
            else:
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
        try:
            os.chdir(mbox.basedir)
        except FileNotFoundError:
            print_info(f"mailbox not found/vanished {mbox.basedir}")
            return

        mboxname = os.path.basename(mbox.basedir)
        if self.verbose:
            date = datetime.fromtimestamp(mbox.last_login) if mbox.last_login else None
            if date:
                print_info(f"checking mailbox {date.strftime('%b %d')} {mboxname}")
            else:
                print_info(f"checking mailbox (no last_login) {mboxname}")
        self.all_files += len(mbox.messages)
        for message in mbox.messages:
            if message.mtime < cutoff_mails:
                self.remove_file(message.relpath, mtime=message.mtime)
            elif message.size > 200000 and message.mtime < cutoff_large_mails:
                # we only remove noticed large files (not unnoticed ones in new/)
                if message.relpath.startswith("cur/"):
                    self.remove_file(message.relpath, mtime=message.mtime)
            else:
                continue
            changed = True
        if changed:
            self.remove_file("maildirsize")

    def get_summary(self):
        return (
            f"Removed {self.del_mboxes} out of {self.all_mboxes} mailboxes "
            f"and {self.del_files} out of {self.all_files} files in existing mailboxes "
            f"in {time.time() - self.start:2.2f} seconds"
        )


def main(args=None):
    """Expire mailboxes and messages according to chatmail config"""
    parser = ArgumentParser(description=main.__doc__)
    ini = "/usr/local/lib/chatmaild/chatmail.ini"
    parser.add_argument(
        "chatmail_ini",
        action="store",
        nargs="?",
        help=f"path pointing to chatmail.ini file, default: {ini}",
        default=ini,
    )
    parser.add_argument(
        "--days", action="store", help="assume date to be days older than now"
    )

    parser.add_argument(
        "--maxnum",
        default=None,
        action="store",
        help="maximum number of mailboxes to iterate on",
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
    args = parser.parse_args(args)

    config = read_config(args.chatmail_ini)
    now = datetime.utcnow().timestamp()
    if args.days:
        now = now - 86400 * int(args.days)

    maxnum = int(args.maxnum) if args.maxnum else None
    exp = Expiry(config, dry=not args.remove, now=now, verbose=args.verbose)
    for mailbox in iter_mailboxes(str(config.mailboxes_dir), maxnum=maxnum):
        exp.process_mailbox_stat(mailbox)
    print(exp.get_summary())


if __name__ == "__main__":
    main(sys.argv[1:])
