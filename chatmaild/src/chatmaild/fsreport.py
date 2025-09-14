import os
from argparse import ArgumentParser
from datetime import datetime

from chatmaild.expire import Stats

DAYSECONDS = 24 * 60 * 60
MONTHSECONDS = DAYSECONDS * 30


def D(timestamp, now=datetime.utcnow().timestamp()):
    diff_seconds = int(now) - int(timestamp)
    # assert diff_seconds >= 0, (int(timestamp), int(now))
    return f"{int(diff_seconds / DAYSECONDS):2.0f}d"


def K(size):
    if size < 1000:
        return f"{size:5.0f}"
    elif size < 10000:
        return f"{size/1000:3.2f}K"
    return f"{int(size/1000):5.0f}K"


def M(size):
    return f"{int(size/1000000):5.0f}M"


def H(size):
    if size < 1000 * 1000:
        return K(size)
    if size < 1000 * 1000 * 1000:
        return M(size)
    return f"{size/1000000000:2.2f}G"


class Report:
    def __init__(self, stats, now):
        self.sum_extra = 0
        self.sum_all_messages = 0
        self.messages = []
        self.user_logins = []
        self.ci_logins = []
        self.stats = stats
        self.now = now

    def process_mailbox_stat(self, mailbox):
        last_login = mailbox.last_login
        if last_login:
            if os.path.basename(mailbox.basedir)[:3] == "ci-":
                self.ci_logins.append(last_login)
            else:
                self.user_logins.append(last_login)
        self.messages.extend(mailbox.messages)
        self.sum_all_messages += sum(msg.size for msg in mailbox.messages)
        self.sum_extra += sum(entry.size for entry in mailbox.extrafiles)

    def dump_summary(self):
        reports = []

        def print_messages(title, messages, num, rep=True):
            print()
            allsize = sum(x.size for x in messages)
            if rep:
                reports.append((title, allsize))

            print(f"## {title} [total: {H(allsize)}]")
            for entry in messages[:num]:
                print(f"{K(entry.size)} {D(entry.mtime)} {entry.relpath}")

        for kind in ("cur", "new"):
            biggest = list(self.messages)
            biggest.sort(key=lambda x: (-x.size, x.mtime))
            print_messages(f"Biggest {kind} messages", biggest, 10, rep=False)

        oldest = self.messages
        mode = "cur"
        for maxsize in (160000, 500000, 2000000, 10000000):
            oldest = [x for x in oldest if x.size > maxsize and mode in x.relpath]
            oldest.sort(key=lambda x: x.mtime)
            print_messages(f"{mode} folders oldest > {K(maxsize)} messages", oldest, 10)

        # list all 160K files of people who haven't logged in for a while
        messages = []
        cutoff_date_login = self.now - 30 * DAYSECONDS
        for mstat in self.stats.mailboxes:
            if mstat.last_login and mstat.last_login < cutoff_date_login:
                for msg in mstat.messages:
                    if msg.size > 160000:
                        messages.append(msg)

        messages.sort(key=lambda x: x.size)
        print_messages(">30-day last_login new >160K", messages, 10)

        print()
        print("## Overall mailbox storage use analysis")
        print(f"Mailbox data: {M(self.sum_extra + self.sum_all_messages)}")
        print(f"Messages    : {M(self.sum_all_messages)}")
        percent = self.sum_extra / (self.sum_extra + self.sum_all_messages) * 100
        print(f"Extra files : {M(self.sum_extra)} ({percent:.2f}%)")

        for title, size in reports:
            percent = size / self.sum_all_messages * 100
            print(f"{title:38} {M(size)} ({percent:.2f}%)")

        all_logins = len(self.user_logins) + len(self.ci_logins)
        num_logins = len(self.user_logins)
        ci_logins = len(self.ci_logins)

        def p(num):
            return f"({num/num_logins * 100:2.2f}%)"

        print()
        print(f"## Login stats, from date reference {datetime.fromtimestamp(self.now)}")
        print(f"all:     {K(all_logins)}")
        print(f"non-ci:  {K(num_logins)}")
        print(f"ci:      {K(ci_logins)}")
        for days in (1, 10, 30, 40, 80, 100, 150):
            active = len(
                [x for x in self.user_logins if x >= self.now - days * DAYSECONDS]
            )
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
        "--days", action="store", help="assume date to be days older than now"
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
    stats = Stats(args.mailboxes_dir, maxnum=maxnum)
    rep = Report(stats, now=now)
    stats.iter_mailboxes(rep.process_mailbox_stat)
    rep.dump_summary()


if __name__ == "__main__":
    main()
