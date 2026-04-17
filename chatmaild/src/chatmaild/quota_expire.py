"""
Remove messages from a mailbox to meet a size target.

Dovecot calls this script when a user's quota is near its limit.
Files are scored by ``size * age`` so that large, old messages
are removed first.

Usage::

    quota_expire <target_mb> <mailbox_path>

"""

import os
import sys
import time
from argparse import ArgumentParser
from collections import namedtuple
from stat import S_ISREG

FileEntry = namedtuple("FileEntry", ("path", "mtime", "size"))


def _get_file_entry(path):
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return None
    if not S_ISREG(st.st_mode):
        return None
    return FileEntry(path, st.st_mtime, st.st_size)


def _listdir(path):
    try:
        return os.listdir(path)
    except FileNotFoundError:
        return []


def scan_mailbox_messages(mailbox_dir):
    messages = []
    for sub in ("cur", "new", "tmp"):
        subdir = f"{mailbox_dir}/{sub}"
        for name in _listdir(subdir):
            entry = _get_file_entry(f"{subdir}/{name}")
            if entry is not None:
                messages.append(entry)
    return messages


def _remove_stale_caches(mailbox_dir):
    for name in ("maildirsize", "dovecot.index.cache"):
        try:
            os.unlink(f"{mailbox_dir}/{name}")
        except FileNotFoundError:
            pass


def expire_to_target(mailbox_dir, target_bytes, now=None):
    """Remove highest-scored files until total size <= *target_bytes*.

    Returns the list of removed file paths.
    """
    if now is None:
        now = time.time()

    messages = scan_mailbox_messages(mailbox_dir)
    total_size = sum(m.size for m in messages)

    if total_size <= target_bytes:
        return []

    # Score: large and old files get the highest score.
    scored = sorted(
        messages,
        key=lambda m: m.size * (now - m.mtime),
        reverse=True,
    )

    removed = []
    for entry in scored:
        if total_size <= target_bytes:
            break
        try:
            os.unlink(entry.path)
        except FileNotFoundError:
            continue
        total_size -= entry.size
        removed.append(entry.path)

    if removed:
        _remove_stale_caches(mailbox_dir)

    return removed


def main(args=None):
    """Remove mailbox messages to stay within a megabyte target."""
    parser = ArgumentParser(description=main.__doc__)
    parser.add_argument(
        "target_mb",
        type=int,
        help="target mailbox size in megabytes",
    )
    parser.add_argument(
        "mailbox_path",
        help="path to a user mailbox, or with --sweep the mailboxes directory",
    )
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="sweep all mailboxes under mailbox_path",
    )
    args = parser.parse_args(args)

    target_bytes = args.target_mb * 1024 * 1024

    if args.sweep:
        return _sweep(args.mailbox_path, target_bytes)

    removed = expire_to_target(args.mailbox_path, target_bytes)
    if removed:
        print(
            f"removed {len(removed)} file(s) from {args.mailbox_path}"
            f" to reach {args.target_mb} MB target",
            file=sys.stderr,
        )
    return 0


def _sweep(mailboxes_dir, target_bytes):
    try:
        names = os.listdir(mailboxes_dir)
    except FileNotFoundError:
        print(f"directory not found: {mailboxes_dir}", file=sys.stderr)
        return 1
    for name in sorted(names):
        if "@" not in name:
            continue
        mbox = f"{mailboxes_dir}/{name}"
        removed = expire_to_target(mbox, target_bytes)
        if removed:
            print(
                f"removed {len(removed)} file(s) from {name}",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
