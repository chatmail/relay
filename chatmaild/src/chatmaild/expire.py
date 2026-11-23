"""
Expire old messages and addresses.

"""

import os
import re
import shutil
import sys
import tempfile
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


def expire_to_target(mbox, target_bytes, dry=False):
    messages = scan_mailbox_messages(mbox)
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
        self.removed_paths = set()
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
        self.removed_paths.add(path)
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
            return False
        elif mbox.last_login is None:
            try:
                if not self.dry:
                    os.rmdir(mbox.basedir)
                    self.del_mboxes += 1
            except OSError:
                print_info(
                    f"Skipped deleting {mbox.basedir}, doesn't have last_login but isn't empty"
                )
            return False

        mboxname = os.path.basename(mbox.basedir)
        if self.verbose:
            date = datetime.fromtimestamp(mbox.last_login) if mbox.last_login else None
            if date:
                print_info(f"checking mailbox {date.strftime('%b %d')} {mboxname}")
            else:
                print_info(f"checking mailbox (no last_login) {mboxname}")
        self.all_files += len(mbox.messages)
        self.removed_paths.clear()
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
        removed = expire_to_target(Path(mbox.basedir), target_bytes, dry=self.dry)
        if removed:
            changed = True
            self.del_files += len(removed)
            self.removed_paths.update(f"{mbox.basedir}/{e.path}" for e in removed)
            if self.verbose:
                print_info(
                    f"quota-expire: removed {len(removed)} message(s) from {mboxname}"
                )

        if changed:
            self.remove_file(f"{mbox.basedir}/maildirsize")
        mbox.messages = [m for m in mbox.messages if m.path not in self.removed_paths]
        return True

    def get_summary(self):
        return (
            f"Removed {self.del_mboxes} out of {self.all_mboxes} mailboxes "
            f"and {self.del_files} out of {self.all_files} files in existing mailboxes "
            f"in {time.time() - self.start:2.2f} seconds"
        )

    def prom_lines(self):
        end = time.time()
        return [
            "# HELP chatmail_expire_removed_mailboxes Mailboxes removed by the last run.",
            "# TYPE chatmail_expire_removed_mailboxes gauge",
            f"chatmail_expire_removed_mailboxes {self.del_mboxes}",
            "# HELP chatmail_expire_removed_files Files removed by the last run.",
            "# TYPE chatmail_expire_removed_files gauge",
            f"chatmail_expire_removed_files {self.del_files}",
            "# HELP chatmail_expire_duration_seconds Duration of the last run.",
            "# TYPE chatmail_expire_duration_seconds gauge",
            f"chatmail_expire_duration_seconds {end - self.start:.2f}",
            "# HELP chatmail_expire_last_run_timestamp_seconds End of the last run.",
            "# TYPE chatmail_expire_last_run_timestamp_seconds gauge",
            f"chatmail_expire_last_run_timestamp_seconds {end:.0f}",
        ]


class Report:
    def __init__(self, now):
        self.size_extra = 0
        self.size_messages = 0
        self.now = now

        self.num_ci_logins = self.num_all_logins = 0
        self.login_buckets = {x: 0 for x in (1, 10, 30, 40, 80, 100, 150)}

        KiB = 1024
        MiB = 1024 * KiB
        self.message_size_thresholds = (
            0,
            100 * KiB,
            MiB // 2,
            1 * MiB,
            2 * MiB,
            5 * MiB,
            10 * MiB,
        )
        self.message_buckets = {x: 0 for x in self.message_size_thresholds}
        self.message_count_buckets = {x: 0 for x in self.message_size_thresholds}

    def process_mailbox_stat(self, mailbox):
        # categorize login times
        last_login = mailbox.last_login
        if last_login:
            self.num_all_logins += 1
            if os.path.basename(mailbox.basedir)[:3] == "ci-":
                self.num_ci_logins += 1
            else:
                for days in self.login_buckets:
                    if last_login >= self.now - days * 86400:
                        self.login_buckets[days] += 1

            # categorize message sizes
            for size in self.message_buckets:
                for msg in mailbox.messages:
                    if msg.size >= size:
                        self.message_buckets[size] += msg.size
                        self.message_count_buckets[size] += 1

        self.size_messages += sum(entry.size for entry in mailbox.messages)
        self.size_extra += sum(entry.size for entry in mailbox.extrafiles)

    def _write_atomic(self, filepath, content):
        """Atomically write content to filepath via tmp+rename."""
        dirpath = os.path.dirname(os.path.abspath(filepath))
        fd, tmppath = tempfile.mkstemp(dir=dirpath, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
            os.chmod(tmppath, 0o644)
            os.rename(tmppath, filepath)
        except BaseException:
            try:
                os.unlink(tmppath)
            except OSError:
                pass
            raise

    def dump_textfile(self, filepath, extra_lines=()):
        """Dump metrics in Prometheus exposition format."""
        lines = []

        lines.append("# HELP chatmail_storage_bytes Mailbox storage in bytes.")
        lines.append("# TYPE chatmail_storage_bytes gauge")
        lines.append(f'chatmail_storage_bytes{{kind="messages"}} {self.size_messages}')
        lines.append(f'chatmail_storage_bytes{{kind="extra"}} {self.size_extra}')
        total = self.size_extra + self.size_messages
        lines.append(f'chatmail_storage_bytes{{kind="total"}} {total}')

        lines.append("# HELP chatmail_messages_bytes Sum of msg bytes >= threshold.")
        lines.append("# TYPE chatmail_messages_bytes gauge")
        for minsize, sumsize in self.message_buckets.items():
            lines.append(f'chatmail_messages_bytes{{min_size="{minsize}"}} {sumsize}')

        lines.append("# HELP chatmail_messages_count Number of msgs >= size threshold.")
        lines.append("# TYPE chatmail_messages_count gauge")
        for minsize, count in self.message_count_buckets.items():
            lines.append(f'chatmail_messages_count{{min_size="{minsize}"}} {count}')

        lines.append("# HELP chatmail_accounts Number of accounts.")
        lines.append("# TYPE chatmail_accounts gauge")
        user_logins = self.num_all_logins - self.num_ci_logins
        lines.append(f'chatmail_accounts{{kind="all"}} {self.num_all_logins}')
        lines.append(f'chatmail_accounts{{kind="ci"}} {self.num_ci_logins}')
        lines.append(f'chatmail_accounts{{kind="user"}} {user_logins}')

        lines.append(
            "# HELP chatmail_accounts_active Non-CI accounts active within N days."
        )
        lines.append("# TYPE chatmail_accounts_active gauge")
        for days, active in self.login_buckets.items():
            lines.append(f'chatmail_accounts_active{{days="{days}"}} {active}')

        lines.extend(extra_lines)
        self._write_atomic(filepath, "\n".join(lines) + "\n")


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
    parser.add_argument(
        "--prom",
        metavar="PATH",
        help="write storage and expiry statistics as Prometheus metrics to PATH",
    )
    args = parser.parse_args(args)

    config = read_config(args.chatmail_ini)
    now = time.time()
    if args.days:
        now = now - 86400 * int(args.days)

    maxnum = int(args.maxnum) if args.maxnum else None
    exp = Expiry(config, dry=not args.remove, now=now, verbose=args.verbose)
    rep = Report(now=now)
    for mailbox in iter_mailboxes(str(config.mailboxes_dir), maxnum=maxnum):
        if exp.process_mailbox_stat(mailbox):
            rep.process_mailbox_stat(mailbox)
    print(exp.get_summary())
    if args.prom:
        rep.dump_textfile(args.prom, extra_lines=exp.prom_lines())


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
