"""
Quota-triggered per-user mailbox cleanup.

Dovecot calls this script via ``quota_warning``
when a user crosses the quota threshold.
The script removes oldest messages first
to keep the mailbox under a specified target size.

Usage::

    chatmail-quota-expire <target_mb> <mailbox_path>

"""

import sys
from argparse import ArgumentParser
from pathlib import Path

from chatmaild.expire import get_file_entry, os_listdir_if_exists


def scan_mailbox_messages(mailbox_dir):
    """Collect FileEntry items from top-level cur/new/tmp only."""
    mbox = Path(mailbox_dir)
    messages = []
    for sub in ("cur", "new", "tmp"):
        for name in os_listdir_if_exists(mbox / sub):
            if entry := get_file_entry(str(mbox / sub / name)):
                messages.append(entry)
    return messages


def expire_to_target(mailbox_dir, target_bytes):
    """Remove oldest files until total size <= *target_bytes*.

    Returns ``(removed_count, cache_bytes)`` where *cache_bytes*
    is the size of the deleted ``dovecot.index.cache`` file
    (0 when the file did not exist).
    """
    mbox = Path(mailbox_dir)
    messages = scan_mailbox_messages(mbox)
    total_size = sum(m.size for m in messages)
    removed = 0
    for count, entry in enumerate(sorted(messages, key=lambda m: m.mtime), 1):
        if total_size <= target_bytes:
            break
        Path(entry.path).unlink(missing_ok=True)
        total_size -= entry.size
        removed = count

    (mbox / "maildirsize").unlink(missing_ok=True)
    cache = mbox / "dovecot.index.cache"
    try:
        cache_bytes = cache.stat().st_size
    except FileNotFoundError:
        cache_bytes = 0
    cache.unlink(missing_ok=True)
    return removed, cache_bytes


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
        help="path to a user mailbox",
    )
    args = parser.parse_args(args)

    target_bytes = args.target_mb * 1024 * 1024

    removed_count, cache_bytes = expire_to_target(args.mailbox_path, target_bytes)
    if removed_count:
        user = Path(args.mailbox_path).name
        cache_mb = cache_bytes / 1024 / 1024
        print(
            f"quota-expire: removed {removed_count} message(s) from {user}"
            f" cache={cache_mb:.1f}MB",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
