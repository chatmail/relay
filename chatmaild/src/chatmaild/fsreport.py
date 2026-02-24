"""
command line tool to analyze mailbox message storage

example invocation:

    python -m chatmaild.fsreport /path/to/chatmail.ini

to show storage summaries for all "cur" folders

    python -m chatmaild.fsreport /path/to/chatmail.ini --mdir cur

to show storage summaries only for first 1000 mailboxes

    python -m chatmaild.fsreport /path/to/chatmail.ini --maxnum 1000

to write Prometheus textfile for node_exporter

    python -m chatmaild.fsreport --textfile /var/lib/prometheus/node-exporter/

writes to /var/lib/prometheus/node-exporter/fsreport.prom

to also write legacy metrics.py style output (default: /var/www/html/metrics):

    python -m chatmaild.fsreport --textfile /var/lib/prometheus/node-exporter/ --legacy-metrics

"""

import os
import tempfile
from argparse import ArgumentParser
from datetime import datetime

from chatmaild.config import read_config
from chatmaild.expire import iter_mailboxes

DAYSECONDS = 24 * 60 * 60
MONTHSECONDS = DAYSECONDS * 30


def HSize(size: int):
    """Format a size integer as a Human-readable string Kilobyte, Megabyte or Gigabyte"""
    if size < 10000:
        return f"{size / 1000:5.2f}K"
    if size < 1000 * 1000:
        return f"{size / 1000:5.0f}K"
    if size < 1000 * 1000 * 1000:
        return f"{int(size / 1000000):5.0f}M"
    return f"{size / 1000000000:5.2f}G"


class Report:
    def __init__(self, now, min_login_age, mdir):
        self.size_extra = 0
        self.size_messages = 0
        self.now = now
        self.min_login_age = min_login_age
        self.mdir = mdir

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
                    if last_login >= self.now - days * DAYSECONDS:
                        self.login_buckets[days] += 1

        cutoff_login_date = self.now - self.min_login_age * DAYSECONDS
        if last_login and last_login <= cutoff_login_date:
            # categorize message sizes
            for size in self.message_buckets:
                for msg in mailbox.messages:
                    if msg.size >= size:
                        if self.mdir and f"/{self.mdir}/" not in msg.path:
                            continue
                        self.message_buckets[size] += msg.size
                        self.message_count_buckets[size] += 1

        self.size_messages += sum(entry.size for entry in mailbox.messages)
        self.size_extra += sum(entry.size for entry in mailbox.extrafiles)

    def dump_summary(self):
        all_messages = self.size_messages
        print()
        print("## Mailbox storage use analysis")
        print(f"Mailbox data total size: {HSize(self.size_extra + all_messages)}")
        print(f"Messages total size    : {HSize(all_messages)}")
        try:
            percent = self.size_extra / (self.size_extra + all_messages) * 100
        except ZeroDivisionError:
            percent = 100
        print(f"Extra files : {HSize(self.size_extra)} ({percent:.2f}%)")

        print()
        if self.min_login_age:
            print(f"### Message storage for {self.min_login_age} days old logins")

        pref = f"[{self.mdir}] " if self.mdir else ""
        for minsize, sumsize in self.message_buckets.items():
            count = self.message_count_buckets[minsize]
            percent = (sumsize / all_messages * 100) if all_messages else 0
            print(
                f"{pref}larger than {HSize(minsize)}: {HSize(sumsize)} ({percent:.2f}%), {count} msgs"
            )

        user_logins = self.num_all_logins - self.num_ci_logins

        def p(num):
            return f"({num / user_logins * 100:2.2f}%)" if user_logins else "100%"

        print()
        print(f"## Login stats, from date reference {datetime.fromtimestamp(self.now)}")
        print(f"all:     {HSize(self.num_all_logins)}")
        print(f"non-ci:  {HSize(user_logins)}")
        print(f"ci:      {HSize(self.num_ci_logins)}")
        for days, active in self.login_buckets.items():
            print(f"last {days:3} days: {HSize(active)} {p(active)}")

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

    def dump_textfile(self, filepath):
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

        self._write_atomic(filepath, "\n".join(lines) + "\n")

    def dump_compat_textfile(self, filepath):
        """Dump legacy metrics.py style metrics."""
        user_logins = self.num_all_logins - self.num_ci_logins
        lines = [
            "# HELP total number of accounts",
            "# TYPE accounts gauge",
            f"accounts {self.num_all_logins}",
            "# HELP number of CI accounts",
            "# TYPE ci_accounts gauge",
            f"ci_accounts {self.num_ci_logins}",
            "# HELP number of non-CI accounts",
            "# TYPE nonci_accounts gauge",
            f"nonci_accounts {user_logins}",
        ]
        self._write_atomic(filepath, "\n".join(lines) + "\n")


def main(args=None):
    """Report about filesystem storage usage of all mailboxes and messages"""
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
        "--days",
        default=0,
        action="store",
        help="assume date to be DAYS older than now",
    )
    parser.add_argument(
        "--min-login-age",
        default=0,
        metavar="DAYS",
        dest="min_login_age",
        action="store",
        help="only sum up message size if last login is at least DAYS days old",
    )
    parser.add_argument(
        "--mdir",
        metavar="{cur,new,tmp}",
        action="store",
        help="only consider messages in specified Maildir subdirectory for summary",
    )

    parser.add_argument(
        "--maxnum",
        default=None,
        action="store",
        help="maximum number of mailboxes to iterate on",
    )
    parser.add_argument(
        "--textfile",
        metavar="PATH",
        default=None,
        help="write Prometheus textfile to PATH (directory or file); "
        "if PATH is a directory, writes 'fsreport.prom' inside it",
    )
    parser.add_argument(
        "--legacy-metrics",
        metavar="FILENAME",
        nargs="?",
        const="/var/www/html/metrics",
        default=None,
        help="write legacy metrics.py textfile (default: /var/www/html/metrics)",
    )

    args = parser.parse_args(args)

    config = read_config(args.chatmail_ini)

    now = datetime.utcnow().timestamp()
    if args.days:
        now = now - 86400 * int(args.days)

    maxnum = int(args.maxnum) if args.maxnum else None
    rep = Report(now=now, min_login_age=int(args.min_login_age), mdir=args.mdir)
    for mbox in iter_mailboxes(str(config.mailboxes_dir), maxnum=maxnum):
        rep.process_mailbox_stat(mbox)
    if args.textfile:
        path = args.textfile
        if os.path.isdir(path):
            path = os.path.join(path, "fsreport.prom")
        rep.dump_textfile(path)
    if args.legacy_metrics:
        rep.dump_compat_textfile(args.legacy_metrics)
    if not args.textfile and not args.legacy_metrics:
        rep.dump_summary()


if __name__ == "__main__":
    main()
