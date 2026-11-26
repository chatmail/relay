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


def expire_to_target(mbox, target_bytes, dry=False, skip=()):
    messages = scan_mailbox_messages(mbox)
    messages = [m for m in messages if str(mbox / m.path) not in skip]
    total_size = sum(m.quota_size for m in messages)
    # Keep recent 24 hours of messages protected from expiry because
    # likely something is wrong with interactions on that address
    # and quota-full signal can help the address owner's device to notice it
    undeletable_messages_cutoff = time.time() - (3600 * 24)
    removed = []
    for entry in sorted(messages):
        if total_size <= target_bytes:
            break
        if entry.mtime > undeletable_messages_cutoff:
            break
        if not dry:
            (mbox / entry.path).unlink(missing_ok=True)
        total_size -= entry.quota_size
        removed.append(entry)

    return removed


def print_info(msg):
    print(msg, file=sys.stderr)


CHATMAIL_VERSION_PATH = "/etc/chatmail-version"


def read_chatmail_version(path):
    """Return (commit, dirty) from the version file that cmdeploy writes."""
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return "unknown", "false"
    commit = lines[0] if lines else "unknown"
    # Lines after the commit hold the `git diff` of the deploying checkout.
    dirty = "true" if len(lines) > 1 else "false"
    return commit, dirty


PROM_HELP = {
    "storage_bytes": "Mailbox storage in bytes.",
    "messages_bytes": "Sum of msg bytes >= threshold.",
    "messages_count": "Number of msgs >= size threshold.",
    "messages_age_bytes": "Sum of msg bytes older than N days.",
    "accounts": "Number of accounts.",
    "accounts_active": "Non-CI accounts active within N days.",
    "expire_removed_mailboxes": "Mailboxes removed by the last run.",
    "expire_removed_files": "Files removed by the last run.",
    "expire_duration_seconds": "Duration of the last run.",
    "expire_last_run_timestamp_seconds": "End of the last run.",
    "version_info": "Deployed relay commit and whether it had local changes.",
}


class Expiry:
    login_days = (1, 10, 30, 40, 80, 100, 150)
    size_thresholds = (0, 100 * 1024, 512 * 1024, 1 << 20, 2 << 20, 5 << 20, 10 << 20)

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
        self.size_messages = self.size_extra = 0
        self.num_ci_logins = self.num_all_logins = 0
        self.login_buckets = dict.fromkeys(self.login_days, 0)
        self.msg_bytes = dict.fromkeys(self.size_thresholds, 0)
        self.msg_counts = dict.fromkeys(self.size_thresholds, 0)
        self.msg_age_bytes = dict.fromkeys((1, 3, 7, 14), 0)

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
        elif mbox.last_login is None:
            try:
                if not self.dry:
                    os.rmdir(mbox.basedir)
                    self.del_mboxes += 1
            except OSError:
                print_info(
                    f"Skipped deleting {mbox.basedir}, doesn't have last_login but isn't empty"
                )
            return

        mboxname = os.path.basename(mbox.basedir)
        if self.verbose:
            date = datetime.fromtimestamp(mbox.last_login) if mbox.last_login else None
            if date:
                print_info(f"checking mailbox {date.strftime('%b %d')} {mboxname}")
            else:
                print_info(f"checking mailbox (no last_login) {mboxname}")
        self.all_files += len(mbox.messages)
        removed_paths = set()
        for message in mbox.messages:
            if message.mtime < cutoff_mails:
                self.remove_file(message.path, mtime=message.mtime)
                removed_paths.add(message.path)
            elif message.size > 200000 and message.mtime < cutoff_large_mails:
                # we only remove noticed large files (not unnoticed ones in new/)
                parts = message.path.split("/")
                if len(parts) >= 2 and parts[-2] == "cur":
                    self.remove_file(message.path, mtime=message.mtime)
                    removed_paths.add(message.path)
            else:
                continue
            changed = True

        target_bytes = (
            self.config.max_mailbox_size_mb * 1024 * 1024 * QUOTA_CLEANUP_FACTOR
        )
        removed = expire_to_target(
            Path(mbox.basedir), target_bytes, dry=self.dry, skip=removed_paths
        )
        if removed:
            changed = True
            self.del_files += len(removed)
            removed_paths.update(f"{mbox.basedir}/{e.path}" for e in removed)
            if self.verbose:
                print_info(
                    f"quota-expire: removed {len(removed)} message(s) from {mboxname}"
                )

        if changed:
            self.remove_file(f"{mbox.basedir}/maildirsize")

        self.num_all_logins += 1
        if mboxname.startswith("ci-"):
            self.num_ci_logins += 1
        else:
            for days in self.login_buckets:
                if mbox.last_login >= self.now - days * 86400:
                    self.login_buckets[days] += 1
        kept = [m for m in mbox.messages if m.path not in removed_paths]
        for size in self.msg_bytes:
            for msg in kept:
                if msg.size >= size:
                    self.msg_bytes[size] += msg.size
                    self.msg_counts[size] += 1
        for days in self.msg_age_bytes:
            cutoff = self.now - days * 86400
            self.msg_age_bytes[days] += sum(m.size for m in kept if m.mtime < cutoff)
        self.size_messages += sum(m.size for m in kept)
        self.size_extra += sum(entry.size for entry in mbox.extrafiles)

    def get_summary(self):
        return (
            f"Removed {self.del_mboxes} out of {self.all_mboxes} mailboxes "
            f"and {self.del_files} out of {self.all_files} files in existing mailboxes "
            f"in {time.time() - self.start:2.2f} seconds"
        )

    def write_prom(self, path):
        end = time.time()
        storage = dict(messages=self.size_messages, extra=self.size_extra)
        storage["total"] = self.size_messages + self.size_extra
        accounts = dict(all=self.num_all_logins, ci=self.num_ci_logins)
        accounts["user"] = accounts["all"] - accounts["ci"]
        help = dict(PROM_HELP)
        tmp = f"{path}.tmp"
        with open(tmp, "w") as f:

            def gauge(name, values, label=None):
                print(f"# HELP chatmail_{name} {help.pop(name)}", file=f)
                print(f"# TYPE chatmail_{name} gauge", file=f)
                for key, value in values.items() if label else [(None, values)]:
                    labels = f'{{{label}="{key}"}}' if label else ""
                    print(f"chatmail_{name}{labels} {value}", file=f)

            gauge("storage_bytes", storage, "kind")
            gauge("messages_bytes", self.msg_bytes, "min_size")
            gauge("messages_count", self.msg_counts, "min_size")
            gauge("messages_age_bytes", self.msg_age_bytes, "min_days")
            gauge("accounts", accounts, "kind")
            gauge("accounts_active", self.login_buckets, "days")
            gauge("expire_removed_mailboxes", self.del_mboxes)
            gauge("expire_removed_files", self.del_files)
            gauge("expire_duration_seconds", f"{end - self.start:.2f}")
            gauge("expire_last_run_timestamp_seconds", f"{end:.0f}")
            commit, dirty = read_chatmail_version(CHATMAIL_VERSION_PATH)
            print(f"# HELP chatmail_version_info {help.pop('version_info')}", file=f)
            print("# TYPE chatmail_version_info gauge", file=f)
            print(
                f'chatmail_version_info{{commit="{commit}",dirty="{dirty}"}} 1', file=f
            )
        assert not help, f"unused PROM_HELP entries: {list(help)}"
        os.replace(tmp, path)


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
    now = time.time()
    if args.days:
        now = now - 86400 * int(args.days)

    maxnum = int(args.maxnum) if args.maxnum else None
    exp = Expiry(config, dry=not args.remove, now=now, verbose=args.verbose)
    for mailbox in iter_mailboxes(str(config.mailboxes_dir), maxnum=maxnum):
        exp.process_mailbox_stat(mailbox)
    print(exp.get_summary())
    if prompath := os.environ.get("CHATMAIL_EXPIRE_PROMPATH"):
        exp.write_prom(prompath)


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

    removed_count = len(expire_to_target(args.mailbox_path, target_bytes))
    if removed_count:
        (args.mailbox_path / "maildirsize").unlink(missing_ok=True)
        print(
            f"quota-expire: removed {removed_count} message(s)"
            f" from {args.mailbox_path.name}",
            file=sys.stderr,
        )
    return 0
