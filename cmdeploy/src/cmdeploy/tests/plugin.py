import imaplib
import itertools
import os
import random
import smtplib
import ssl
import subprocess
import time
from pathlib import Path

import pytest
from chatmaild.config import read_config

conftestdir = Path(__file__).parent


def pytest_addoption(parser):
    parser.addoption(
        "--slow", action="store_true", default=False, help="also run slow tests"
    )


def pytest_configure(config):
    config._benchresults = {}
    config.addinivalue_line(
        "markers", "slow: mark test to require --slow option to run"
    )


def pytest_runtest_setup(item):
    markers = list(item.iter_markers(name="slow"))
    if markers:
        if not item.config.getoption("--slow"):
            pytest.skip("skipping slow test, use --slow to run")


def _get_chatmail_config():
    current = Path().resolve()
    while 1:
        path = current.joinpath("chatmail.ini").resolve()
        if path.exists():
            return read_config(path), path
        if current == current.parent:
            break
        current = current.parent
    return None, None


@pytest.fixture(scope="session")
def chatmail_config(pytestconfig):
    config, path = _get_chatmail_config()
    if config:
        return config
    basedir = Path().resolve()
    pytest.skip(f"no chatmail.ini file found in {basedir} or parent dirs")


@pytest.fixture(scope="session")
def maildomain(chatmail_config):
    return chatmail_config.mail_domain


@pytest.fixture(scope="session")
def sshdomain(maildomain):
    return os.environ.get("CHATMAIL_SSH", maildomain)


@pytest.fixture
def maildomain2():
    domain = os.environ.get("CHATMAIL_DOMAIN2")
    if not domain:
        pytest.skip("set CHATMAIL_DOMAIN2 to a second chatmail server")
    return domain


@pytest.fixture
def sshdomain2(maildomain2):
    return os.environ.get("CHATMAIL_SSH2", maildomain2)


def pytest_report_header():
    config, path = _get_chatmail_config()
    domain2 = os.environ.get("CHATMAIL_DOMAIN2", "NOT SET")
    domain = config.mail_domain if config else "NOT SET"
    path = path if path else "NOT SET"

    lines = [
        f"chatmail.ini {domain} location: {path}",
        f"chatmail2: {domain2}",
    ]
    sep = "-" * max(map(len, lines))
    return [sep, *lines, sep]


@pytest.fixture
def cm_data(request):
    datadir = request.fspath.dirpath("data")

    class CMData:
        def get(self, name):
            return datadir.join(name).read()

    return CMData()


@pytest.fixture
def benchmark(request, chatmail_config):
    def bench(func, num, name=None, reportfunc=None, cooldown=0.0):
        if name is None:
            name = func.__name__
        if cooldown == "auto":
            per_minute = max(chatmail_config.max_user_send_per_minute, 1)
            cooldown = chatmail_config.max_user_send_burst_size * 60 / per_minute

        durations = []
        for i in range(num):
            now = time.time()
            func()
            durations.append(time.time() - now)
            if cooldown > 0 and i + 1 < num:
                # Keep post-run cooldown out of measured benchmark duration.
                time.sleep(cooldown)
        durations.sort()
        request.config._benchresults[name] = (reportfunc, durations)

    return bench


def pytest_terminal_summary(terminalreporter):
    tr = terminalreporter
    results = tr.config._benchresults
    if not results:
        return

    tr.section("benchmark results")
    float_names = "median min max".split()
    width = max(map(len, float_names))

    def fcol(parts):
        return " ".join(part.rjust(width) for part in parts)

    headers = f"{'benchmark name': <30} " + fcol(float_names)
    tr.write_line(headers)
    tr.write_line("-" * len(headers))
    summary_lines = []

    for name, (reportfunc, durations) in results.items():
        measures = [
            sorted(durations)[len(durations) // 2],
            min(durations),
            max(durations),
        ]
        line = f"{name: <30} "
        line += fcol(f"{float: 2.2f}" for float in measures)
        tr.write_line(line)
        vmedian, vmin, vmax = measures
        if reportfunc:
            for line in reportfunc(vmin=vmin, vmedian=vmedian, vmax=vmax):
                summary_lines.append(line)

    if summary_lines:
        tr.write_line("")
        tr.section("benchmark summary measures")
        for line in summary_lines:
            tr.write_line(line)


@pytest.fixture(scope="session")
def ssl_context(chatmail_config):
    if chatmail_config.tls_cert_mode == "self":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


@pytest.fixture
def imap(maildomain, ssl_context):
    return ImapConn(maildomain, ssl_context=ssl_context)


@pytest.fixture
def make_imap_connection(maildomain, ssl_context):
    def make_imap_connection():
        conn = ImapConn(maildomain, ssl_context=ssl_context)
        conn.connect()
        return conn

    return make_imap_connection


class ImapConn:
    AuthError = imaplib.IMAP4.error
    logcmd = "journalctl -f -u dovecot"
    name = "dovecot"

    def __init__(self, host, ssl_context=None):
        self.host = host
        self.ssl_context = ssl_context

    def connect(self):
        print(f"imap-connect {self.host}")
        self.conn = imaplib.IMAP4_SSL(self.host, ssl_context=self.ssl_context)

    def login(self, user, password):
        print(f"imap-login {user!r} {password!r}")
        self.conn.login(user, password)

    def fetch_all(self):
        print("imap-fetch all")
        status, res = self.conn.select()
        if int(res[0]) == 0:
            raise ValueError("no messages in imap folder")
        status, results = self.conn.fetch("1:*", "(RFC822)")
        assert status == "OK"
        return results

    def fetch_all_messages(self):
        print("imap-fetch all messages")
        results = self.fetch_all()
        messages = []
        for item in results:
            if len(item) == 2:
                messages.append(item[1].decode())
        return messages


@pytest.fixture
def smtp(maildomain, ssl_context):
    return SmtpConn(maildomain, ssl_context=ssl_context)


@pytest.fixture
def make_smtp_connection(maildomain, ssl_context):
    def make_smtp_connection():
        conn = SmtpConn(maildomain, ssl_context=ssl_context)
        conn.connect()
        return conn

    return make_smtp_connection


class SmtpConn:
    AuthError = smtplib.SMTPAuthenticationError
    logcmd = "journalctl -f -t postfix/smtpd -t postfix/smtp -t postfix/lmtp"
    name = "postfix"

    def __init__(self, host, ssl_context=None):
        self.host = host
        self.ssl_context = ssl_context

    def connect(self):
        print(f"smtp-connect {self.host}")
        context = self.ssl_context or ssl.create_default_context()
        self.conn = smtplib.SMTP_SSL(self.host, context=context)

    def login(self, user, password):
        print(f"smtp-login {user!r} {password!r}")
        self.conn.login(user, password)

    def sendmail(self, from_addr, to_addrs, msg):
        print(f"smtp-sendmail from={from_addr!r} to_addrs={to_addrs!r}")
        print(f"smtp-sendmail message size: {len(msg)}")
        return self.conn.sendmail(from_addr=from_addr, to_addrs=to_addrs, msg=msg)


@pytest.fixture(params=["imap", "smtp"])
def imap_or_smtp(request):
    return request.getfixturevalue(request.param)


@pytest.fixture
def gencreds(chatmail_config):
    count = itertools.count()
    next(count)

    def gen(domain=None):
        domain = domain if domain else chatmail_config.mail_domain
        while 1:
            num = next(count)
            alphanumeric = "abcdefghijklmnopqrstuvwxyz1234567890"
            user = "".join(
                random.choices(alphanumeric, k=chatmail_config.username_max_length)
            )
            if domain == "nine.testrun.org":
                user = f"ac{num}_{user}"[:9]
            else:
                user = f"ac{num}_{user}"[: chatmail_config.username_max_length]
            password = "".join(
                random.choices(alphanumeric, k=chatmail_config.password_min_length)
            )
            yield f"{user}@{domain}", f"{password}"

    return lambda domain=None: next(gen(domain))


#
# Delta Chat RPC-based test support
# use the cmfactory fixture to get chatmail instance accounts
#

from deltachat_rpc_client import DeltaChat, Rpc


class ChatmailACFactory:
    """RPC-based account factory for chatmail testing."""

    def __init__(self, rpc, maildomain, gencreds, chatmail_config):
        self.dc = DeltaChat(rpc)
        self.rpc = rpc
        self._maildomain = maildomain
        self.gencreds = gencreds
        self.chatmail_config = chatmail_config

    def _make_transport(self, domain):
        """Build a transport config dict for the given domain."""
        addr, password = self.gencreds(domain)
        transport = {
            "addr": addr,
            "password": password,
            # Setting server explicitly skips requesting autoconfig XML,
            # see https://datatracker.ietf.org/doc/draft-ietf-mailmaint-autoconfig/
            "imapServer": domain,
            "smtpServer": domain,
        }
        if self.chatmail_config.tls_cert_mode == "self":
            transport["certificateChecks"] = "acceptInvalidCertificates"
        return transport

    def get_online_account(self, domain=None):
        """Create, configure and bring online a single account."""
        return self.get_online_accounts(1, domain)[0]

    def get_online_accounts(self, num, domain=None):
        """Create multiple online accounts in parallel."""
        domain = domain or self._maildomain
        futures = []
        accounts = []
        for _ in range(num):
            account = self.dc.add_account()
            future = account.add_or_update_transport.future(
                self._make_transport(domain)
            )
            futures.append(future)

            # ensure messages stay in INBOX so that they can be
            # concurrently fetched via extra IMAP connections during tests
            account.set_config("delete_server_after", "10")
            accounts.append(account)

        for future in futures:
            future()

        for account in accounts:
            account.bring_online()
        return accounts

    def get_accepted_chat(self, ac1, ac2):
        """Create a 1:1 chat between ac1 and ac2 accepted on both sides."""
        ac2.create_chat(ac1)
        return ac1.create_chat(ac2)


@pytest.fixture(scope="session")
def rpc(tmp_path_factory):
    """Start a deltachat-rpc-server process for the test session."""

    # NB: accounts_dir must NOT already exist as directory --
    # core-rust only creates accounts.toml if the dir doesn't exist yet.
    accounts_dir = str(tmp_path_factory.mktemp("dc") / "accounts")
    rpc = Rpc(accounts_dir=accounts_dir)
    rpc.start()
    yield rpc
    rpc.close()


@pytest.fixture
def cmfactory(rpc, gencreds, maildomain, chatmail_config):
    """Return a ChatmailACFactory for creating online Delta Chat accounts."""
    return ChatmailACFactory(
        rpc=rpc,
        maildomain=maildomain,
        gencreds=gencreds,
        chatmail_config=chatmail_config,
    )


@pytest.fixture
def remote(sshdomain):
    r = Remote(sshdomain)
    yield r
    r.close()


class Remote:
    def __init__(self, sshdomain):
        self.sshdomain = sshdomain
        self._procs = []

    def iter_output(self, logcmd="", ready=None):
        getjournal = "journalctl -f" if not logcmd else logcmd
        print(self.sshdomain)
        match self.sshdomain:
            case "@local": command = []
            case "localhost": command = []
            case _: command = ["ssh", f"root@{self.sshdomain}"]
        [command.append(arg) for arg in getjournal.split()]
        popen = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self._procs.append(popen)
        try:
            while 1:
                line = popen.stdout.readline()
                res = line.decode().strip().lower()
                if not res:
                    break
                if ready is not None:
                    ready()
                    ready = None
                yield res
        finally:
            popen.terminate()
            popen.wait()

    def close(self):
        while self._procs:
            proc = self._procs.pop()
            proc.kill()
            proc.wait()


@pytest.fixture
def lp(request):
    class LP:
        def sec(self, msg):
            print(f"---- {msg} ----")

        def indent(self, msg):
            print(f"     {msg}")

    return LP()


@pytest.fixture
def cmsetup(maildomain, gencreds, ssl_context):
    return CMSetup(maildomain, gencreds, ssl_context)


class CMSetup:
    def __init__(self, maildomain, gencreds, ssl_context):
        self.maildomain = maildomain
        self.gencreds = gencreds
        self.ssl_context = ssl_context

    def gen_users(self, num):
        print(f"Creating {num} online users")
        users = []
        for i in range(num):
            addr, password = self.gencreds()
            user = CMUser(self.maildomain, addr, password, self.ssl_context)
            assert user.smtp
            users.append(user)
        return users


class CMUser:
    def __init__(self, maildomain, addr, password, ssl_context=None):
        self.maildomain = maildomain
        self.addr = addr
        self.password = password
        self.ssl_context = ssl_context
        self._smtp = None
        self._imap = None

    @property
    def smtp(self):
        if not self._smtp:
            handle = SmtpConn(self.maildomain, ssl_context=self.ssl_context)
            handle.connect()
            handle.login(self.addr, self.password)
            self._smtp = handle
        return self._smtp

    @property
    def imap(self):
        if not self._imap:
            imap = ImapConn(self.maildomain, ssl_context=self.ssl_context)
            imap.connect()
            imap.login(self.addr, self.password)
            self._imap = imap
        return self._imap
