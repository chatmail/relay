import sys
import os
import shutil
import logging
import time
from stat import S_ISREG
from pathlib import Path
from datetime import datetime
from collections import namedtuple

# delete already seen big mails after 7 days, in the INBOX
# 2 0 * * * vmail find {{ config.mailboxes_dir }} -path '*/cur/*' -mtime +{{ config.delete_large_after }} -size +200k -type f -delete
# # delete all mails after {{ config.delete_mails_after }} days, in the Inbox
# 2 0 * * * vmail find {{ config.mailboxes_dir }} -path '*/cur/*' -mtime +{{ config.delete_mails_after }} -type f -delete
## or in any IMAP subfolder
# 2 0 * * * vmail find {{ config.mailboxes_dir }} -path '*/.*/cur/*' -mtime +{{ config.delete_mails_after }} -type f -delete
## even if they are unseen
# 2 0 * * * vmail find {{ config.mailboxes_dir }} -path '*/new/*' -mtime +{{ config.delete_mails_after }} -type f -delete
# 2 0 * * * vmail find {{ config.mailboxes_dir }} -path '*/.*/new/*' -mtime +{{ config.delete_mails_after }} -type f -delete
## or only temporary (but then they shouldn't be around after {{ config.delete_mails_after }} days anyway).
# 2 0 * * * vmail find {{ config.mailboxes_dir }} -path '*/tmp/*' -mtime +{{ config.delete_mails_after }} -type f -delete
# 2 0 * * * vmail find {{ config.mailboxes_dir }} -path '*/.*/tmp/*' -mtime +{{ config.delete_mails_after }} -type f -delete
# 3 0 * * * vmail find {{ config.mailboxes_dir }} -name 'maildirsize' -type f -delete


FileEntry = namedtuple("FileEntry", ["relpath", "mtime", "size"])
dayseconds = 24 * 60 * 60
monthseconds = dayseconds * 30


def joinpath(name, extra):
    return name + "/" + extra


def D(timestamp, now=datetime.utcnow().timestamp()):
    diff_seconds = int(now) - int(timestamp)
    # assert diff_seconds >= 0, (int(timestamp), int(now))
    return f"{int(diff_seconds / dayseconds):2.0f}d"


def K(size):
    return f"{int(size/1000):6.0f}K"


def M(size):
    return f"{int(size/1000000):6.0f}M"


now = datetime.utcnow().timestamp()


class Stats:
    def __init__(self, basedir):
        self.basedir = str(basedir)
        self.mailboxes = []

    def iter_mailboxes(self, maxnum=None):
        for mailbox in os.listdir(self.basedir)[:maxnum]:
            if "@" in mailbox:
                mailboxdir = joinpath(self.basedir, mailbox)
                self.mailboxes.append(MailboxStat(mailboxdir))


class MailboxStat:
    def __init__(self, mailboxdir):
        self.mailboxdir = mailboxdir = str(mailboxdir)
        self.messages = []
        self.extrafiles = []

        for name in os.listdir(mailboxdir):
            fpath = joinpath(mailboxdir, name)
            if name in ("cur", "new", "tmp"):
                for msg_name in os.listdir(fpath):
                    msg_path = joinpath(fpath, msg_name)
                    st = os.stat(msg_path)
                    relpath = joinpath(name, msg_name)
                    self.messages.append(
                        FileEntry(relpath, mtime=st.st_mtime, size=st.st_size)
                    )
            else:
                st = os.stat(fpath)
                if S_ISREG(st.st_mode):
                    self.extrafiles.append(FileEntry(name, st.st_mtime, st.st_size))
        self.extrafiles.sort(key=lambda x: x.size, reverse=True)

    @property
    def last_login(self):
        for entry in self.extrafiles:
            if entry.relpath == "password":
                return entry.mtime

    def get_messages(self, prefix=""):
        l = []
        for entry in self.messages:
            if entry.relpath.startswith(prefix):
                l.append(entry)
        return l

    def get_extra_files(self):
        return list(self.extrafiles)


class XXXStats:
    def __init__(self):
        self.sum_extra = 0
        self.sum_all_messages = 0
        self.logins = []
        self.messages = []

    def analyze(self, statscache):
        print("start")
        for mailbox in statscache.cache:
            mbox_cache = statscache.cache[mailbox]
            if "password" not in mbox_cache:
                continue
            self.logins.append(mbox_cache["password"][0])
            for relpath, (mtime, size) in mbox_cache.items():
                if relpath[:4] in ("cur/", "new/", "tmp/"):
                    self.sum_all_messages += size
                    entry = FileEntry(relpath=relpath, mtime=mtime, size=size)
                    self.messages.append(entry)
                else:
                    self.sum_extra += size

    def dump_summary(self):
        print(f"size of everything: {M(self.sum_extra + self.sum_all_messages)}")
        print(f"size all messages:  {M(self.sum_all_messages)}")
        percent = self.sum_extra / (self.sum_extra + self.sum_all_messages) * 100
        print(f"size extra files:   {M(self.sum_extra)} ({percent:.2f}%)")
        for size in (100000, 200000, 500000, 1000000, 5000000):
            all_of_size = sum(
                x.size
                for x in self.messages
                if x.size > size and x.relpath.startswith("cur")
            )
            percent = all_of_size / self.sum_all_messages * 100
            print(f"size seen {K(size)} messages: {M(all_of_size)} ({percent:.2f}%)")
        for size in (100000, 200000, 500000, 1000000, 5000000):
            all_of_size = sum(
                x.size
                for x in self.messages
                if x.size > size and x.mtime < now - 2 * dayseconds
            )
            percent = all_of_size / self.sum_all_messages * 100
            print(
                f"size 2day-old {K(size)} messages: {M(all_of_size)} ({percent:.2f}%)"
            )
        for size in (100000, 200000, 500000, 1000000, 5000000):
            all_of_size = sum(
                x.size
                for x in self.messages
                if x.size > size
                and x.relpath.startswith("cur")
                and x.mtime < now - 7 * dayseconds
            )
            percent = all_of_size / self.sum_all_messages * 100
            print(
                f"size seen 7-day old {K(size)} messages: {M(all_of_size)} ({percent:.2f}%)"
            )

        print()

        num_logins = len(self.logins)
        monthly_active = len([x for x in self.logins if x >= now - monthseconds])
        daily_active = len([x for x in self.logins if x >= now - dayseconds])
        stale = num_logins - monthly_active

        def p(num):
            return f"({num/num_logins * 100:.2f}%)"

        print(f"all logins:     {K(num_logins)}")
        print(f"monthly active: {K(monthly_active)} {p(monthly_active)}")
        print(f">1m old logins: {K(stale)} {p(stale)}")
        print(f"daily active:   {K(daily_active)} {p(daily_active)}")


def run_expire(config, basedir):
    stat = Stats(basedir)
    stat.iter_mailboxes()
    cutoff_date = time.time() - config.delete_inactive_users_after * 86400

    num = 0
    for mbox in stat.mailboxes:
        if mbox.last_login < cutoff_date:
            logging.info("removing outdated mailbox %s", mbox.mailboxdir)
            shutil.rmtree(mbox.mailboxdir, ignore_errors=True)
            num += 1
    print(f"expired {num} mailboxes")


if __name__ == "__main__":
    cfgpath, basedir = sys.argv[1:]
    config = read_config(cfgpath)
    run_expire(config, basedir)
