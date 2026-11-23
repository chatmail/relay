"""Mailbox storage statistics for chatmail-expire --prom."""

import os
import tempfile

DAYSECONDS = 24 * 60 * 60


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
                    if last_login >= self.now - days * DAYSECONDS:
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
