"""
command line tool to analyze mailbox message storage

example invocation:

    python -m chatmaild.fsreport /home/vmail/mail/nine.testrun.org

to show storage summaries for all "cur" folders

    python -m chatmaild.fsreport /home/vmail/mail/nine.testrun.org --mdir cur

to show storage summaries only for first 1000 mailboxes

    python -m chatmaild.fsreport /home/vmail/mail/nine.testrun.org --maxnum 1000

"""

import os
from argparse import ArgumentParser
from datetime import datetime

from chatmaild.expire import iter_mailboxes

DAYSECONDS = 24 * 60 * 60
MONTHSECONDS = DAYSECONDS * 30


def D(timestamp, now=datetime.utcnow().timestamp()):
    diff_seconds = int(now) - int(timestamp)
    # assert diff_seconds >= 0, (int(timestamp), int(now))
    return f"{int(diff_seconds / DAYSECONDS):2.0f}d"


def K(size):
    if size < 1000:
        return f"{size:6.0f}"
    elif size < 10000:
        return f"{size / 1000:3.2f}K"
    return f"{int(size / 1000):5.0f}K"


def M(size):
    return f"{int(size / 1000000):5.0f}M"


def H(size):
    if size < 1000 * 1000:
        return K(size)
    if size < 1000 * 1000 * 1000:
        return M(size)
    return f"{size / 1000000000:2.2f}G"


class Report:
    def __init__(self, now, min_login_age, mdir):
        self.size_extra = 0
        self.size_messages = 0
        self.now = now
        self.min_login_age = min_login_age
        self.mdir = mdir

        self.num_ci_logins = self.num_all_logins = 0
        self.login_buckets = dict((x, 0) for x in (1, 10, 30, 40, 80, 100, 150))
        self.message_buckets = dict((x, 0) for x in (0, 160000, 500000, 2000000))

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
                        if self.mdir and not msg.relpath.startswith(self.mdir):
                            continue
                        self.message_buckets[size] += msg.size

        self.size_messages += sum(entry.size for entry in mailbox.messages)
        self.size_extra += sum(entry.size for entry in mailbox.extrafiles)

    def dump_summary(self):
        all_messages = self.size_messages
        print()
        print("## Mailbox storage use analysis")
        print(f"Mailbox data total size: {M(self.size_extra + all_messages)}")
        print(f"Messages total size    : {M(all_messages)}")
        percent = self.size_extra / (self.size_extra + all_messages) * 100
        print(f"Extra files : {M(self.size_extra)} ({percent:.2f}%)")

        print()
        if self.min_login_age:
            print(f"### Message storage for {self.min_login_age} days old logins")

        pref = f"[{self.mdir}] " if self.mdir else ""
        for minsize, sumsize in self.message_buckets.items():
            percent = sumsize / all_messages * 100
            print(f"{pref}larger than {K(minsize)}: {M(sumsize)} ({percent:.2f}%)")

        user_logins = self.num_all_logins - self.num_ci_logins

        def p(num):
            return f"({num / user_logins * 100:2.2f}%)"

        print()
        print(f"## Login stats, from date reference {datetime.fromtimestamp(self.now)}")
        print(f"all:     {K(self.num_all_logins)}")
        print(f"non-ci:  {K(user_logins)}")
        print(f"ci:      {K(self.num_ci_logins)}")
        for days, active in self.login_buckets.items():
            print(f"last {days:3} days: {K(active)} {p(active)}")


def main(args=None):
    """Report about filesystem storage usage of all mailboxes and messages"""
    parser = ArgumentParser(description=main.__doc__)
    # parser.add_argument(
    #    "chatmail_ini", action="store", help="path pointing to chatmail.ini file"
    # )
    parser.add_argument(
        "mailboxes_dir", action="store", help="path to directory of mailboxes"
    )
    parser.add_argument(
        "--days",
        default=0,
        action="store",
        help="assume date to be days older than now",
    )
    parser.add_argument(
        "--min-login-age",
        default=0,
        dest="min_login_age",
        action="store",
        help="only sum up message size if last login is at least min-login-age days old",
    )
    parser.add_argument(
        "--mdir",
        action="store",
        help="only consider 'cur' or 'new' or 'tmp' messages for summary",
    )

    parser.add_argument(
        "--maxnum",
        default=None,
        action="store",
        help="maximum number of mailbxoes to iterate on",
    )

    args = parser.parse_args([str(x) for x in args] if args else args)

    now = datetime.utcnow().timestamp()
    if args.days:
        now = now - 86400 * int(args.days)

    maxnum = int(args.maxnum) if args.maxnum else None
    rep = Report(now=now, min_login_age=int(args.min_login_age), mdir=args.mdir)
    for mbox in iter_mailboxes(os.path.abspath(args.mailboxes_dir), maxnum=maxnum):
        rep.process_mailbox_stat(mbox)
    rep.dump_summary()


if __name__ == "__main__":
    main()
