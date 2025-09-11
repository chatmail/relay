import os
import shutil
import sys
import time
from collections import namedtuple
from datetime import datetime
from stat import S_ISREG

from chatmaild.config import read_config

# delete already seen big mails after 7 days, in the INBOX
# 2 0 * * * vmail find {{ config.mailboxes_dir }} -path '*/cur/*' -mtime +{{ config.delete_large_after }} -size +200k -type f -delete
# # delete all mails after {{ config.delete_mails_after }} days, in the Inbox
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


class Stats:
    def __init__(self, basedir, maxnum=None):
        self.basedir = str(basedir)
        self.mailboxes = []
        self.maxnum = maxnum

    def iter_mailboxes(self):
        for mailbox in os.listdir(self.basedir)[: self.maxnum]:
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

    def get_file_entry(self, name):
        for entry in self.extrafiles:
            if name == entry.relapth:
                return entry


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
        now = datetime.utcnow().timestamp()

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


def run_expire(config, basedir, dry=False, maxnum=None):
    now = time.time()

    stat = Stats(basedir, maxnum=maxnum)
    stat.iter_mailboxes()
    cutoff_date_without_login = now - int(config.delete_inactive_users_after) * 86400
    cutoff_date_mails = now - int(config.delete_mails_after) * 86400
    cutoff_date_large_mails = now - int(config.delete_large_after) * 86400

    def rmtree(path):
        if dry:
            print("would remove mailbox", path)
        else:
            shutil.rmtree(path, ignore_errors=True)

    def unlink(mailboxdir, message):
        if dry:
            relpath = os.path.basename(mailboxdir) + message.relpath
            print(f"would remove {D(message.mtime)} {K(message.size)} {relpath}")
        else:
            os.unlink(path)

    for mbox in stat.mailboxes:
        changed = False
        if mbox.last_login and mbox.last_login < cutoff_date_without_login:
            rmtree(mbox.mailboxdir)
            continue
        for message in mbox.messages:
            path = joinpath(mbox.mailboxdir, message.relpath)
            if message.mtime < cutoff_date_mails:
                unlink(mbox.mailboxdir, message)
            elif message.size > 200000 and message.mtime < cutoff_date_large_mails:
                unlink(mbox.mailboxdir, message)
            else:
                continue
            changed = True
        if changed and not dry:
            p = joinpath(mbox.mailboxdir, "maildirsize")
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass


def main():
    cfgpath, basedir, maxnum = sys.argv[1:]
    config = read_config(cfgpath)
    run_expire(config, basedir, dry=True, maxnum=int(maxnum))


if __name__ == "__main__":
    main()
