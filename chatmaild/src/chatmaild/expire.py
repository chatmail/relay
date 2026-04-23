"""
Expire old messages and addresses.

"""

import os
import re
import shutil
import sys
import time
from argparse import ArgumentParser
from collections import namedtuple
from datetime import datetime
from pathlib import Path
from stat import S_ISREG

from chatmaild.config import read_config

FileEntry = namedtuple("FileEntry", ("path", "mtime", "size"))
QuotaFileEntry = namedtuple("QuotaFileEntry", ("mtime", "quota_size", "path"))

# Quota cleanup factor of max_mailbox_size. The mailbox is reset to this size.
QUOTA_CLEANUP_FACTOR = 0.7

# e.g. "cur/1775324677.M448978P3029757.exam,S=3235,W=3305:2,S"
_dovecot_fn_rex = re.compile(r".+/(\d+)\..+,S=(\d+)")


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
        self.messages = []
        self.extrafiles = []
        self.scandir(self.basedir)

    def scandir(self, folderdir):
        for name in os_listdir_if_exists(folderdir):
            path = f"{folderdir}/{name}"
            if name in ("cur", "new", "tmp"):
                for msg_name in os_listdir_if_exists(path):
                    entry = get_file_entry(f"{path}/{msg_name}")
                    if entry is not None:
                        self.messages.append(entry)
            elif os.path.isdir(path):
                self.scandir(path)
            else:
                entry = get_file_entry(path)
                if entry is not None:
                    self.extrafiles.append(entry)
                    if name == "password":
                        self.last_login = entry.mtime
        self.extrafiles.sort(key=lambda x: -x.size)


def parse_dovecot_filename(relpath):
    m = _dovecot_fn_rex.match(relpath)
    if not m:
        return None
    return QuotaFileEntry(int(m.group(1)), int(m.group(2)), relpath)


def scan_mailbox_messages(mbox):
    messages = []
    for sub in ("cur", "new"):
        for name in os_listdir_if_exists(mbox / sub):
            if entry := parse_dovecot_filename(f"{sub}/{name}"):
                messages.append(entry)
    return messages


def expire_to_target(mbox, target_bytes):
    messages = scan_mailbox_messages(mbox)
    total_size = sum(m.quota_size for m in messages)
    removed = 0
    for entry in sorted(messages):
        if total_size <= target_bytes:
            break
        (mbox / entry.path).unlink(missing_ok=True)
        total_size -= entry.quota_size
        removed += 1

    return removed


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
                self.remove_file(message.path, mtime=message.mtime)
            elif message.size > 200000 and message.mtime < cutoff_large_mails:
                # we only remove noticed large files (not unnoticed ones in new/)
                parts = message.path.split("/")
                if len(parts) >= 2 and parts[-2] == "cur":
                    self.remove_file(message.path, mtime=message.mtime)
            else:
                continue
            changed = True

        target_bytes = (
            self.config.max_mailbox_size_mb * 1024 * 1024 * QUOTA_CLEANUP_FACTOR
        )
        removed = expire_to_target(Path(mbox.basedir), target_bytes)
        if removed:
            changed = True
            self.del_files += removed
            if self.verbose:
                print_info(
                    f"quota-expire: removed {removed} message(s) from {mboxname}"
                )

        if changed:
            self.remove_file(f"{mbox.basedir}/maildirsize")

    def get_summary(self):
        return (
            f"Removed {self.del_mboxes} out of {self.all_mboxes} mailboxes "
            f"and {self.del_files} out of {self.all_files} files in existing mailboxes "
            f"in {time.time() - self.start:2.2f} seconds"
        )


def daily_expire_main(args=None):
    """Expire mailboxes and messages according to chatmail config"""
    parser = ArgumentParser(description=daily_expire_main.__doc__)
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


def quota_expire_main(args=None):
    """Remove mailbox messages to stay within a megabyte target.

    This entry point is called by dovecot when a quota threshold is passed.
    """

    parser = ArgumentParser(description=quota_expire_main.__doc__)
    parser.add_argument(
        "target_mb",
        type=int,
        help="target mailbox size in megabytes",
    )
    parser.add_argument(
        "mailbox_path",
        type=Path,
        help="path to a user mailbox",
    )
    args = parser.parse_args(args)

    target_bytes = args.target_mb * 1024 * 1024

    removed_count = expire_to_target(args.mailbox_path, target_bytes)
    if removed_count:
        (args.mailbox_path / "maildirsize").unlink(missing_ok=True)
        print(
            f"quota-expire: removed {removed_count} message(s)"
            f" from {args.mailbox_path.name}",
            file=sys.stderr,
        )
    return 0
