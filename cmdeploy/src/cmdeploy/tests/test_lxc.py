"""Tests for cmdeploy lxc-* subcommands."""

import shutil
import subprocess
import sys

import pytest

from cmdeploy.lxc import cli
from cmdeploy.lxc.incus import Incus

pytestmark = pytest.mark.skipif(
    not shutil.which("incus") or not shutil.which("lxc"),
    reason="incus/lxc not installed",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ix():
    return Incus()


@pytest.fixture(scope="session")
def lxc_setup():
    ix = Incus()
    ix.get_dns_container().ensure()
    return ix.list_managed()


@pytest.fixture(scope="session")
def relay_container(lxc_setup):
    test_names = {f"{n}-localchat" for n in cli.RELAY_NAMES}
    relays = [c for c in lxc_setup if c["name"] in test_names and c.get("ip")]
    if not relays:
        pytest.skip("no test relay containers running")
    return relays[0]


@pytest.fixture
def cmdeploy():

    def run(*args):
        return subprocess.run(
            [sys.executable, "-m", "cmdeploy.cmdeploy", *args],
            capture_output=True,
            text=True,
            check=False,
        )

    return run


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subcmd, expected, absent",
    [
        (None, ["lxc-start", "lxc-stop", "lxc-test", "lxc-status"], ["lxc-destroy"]),
        ("lxc-start", ["--ipv4-only", "--run"], ["--config"]),
        ("lxc-stop", ["--destroy", "--destroy-all"], ["--config"]),
        ("lxc-test", ["--one"], ["--config"]),
        ("lxc-status", [], ["--config"]),
        ("run", ["--ssh-config"], ["--lxc"]),
        ("dns", ["--ssh-config"], []),
        ("test", ["--ssh-config"], []),
        ("status", ["--ssh-config"], []),
    ],
)
def test_help_options(cmdeploy, subcmd, expected, absent):
    args = [subcmd, "--help"] if subcmd else ["--help"]
    result = cmdeploy(*args)
    output = result.stdout + result.stderr
    assert result.returncode == 0
    for flag in expected:
        assert flag in output
    for flag in absent:
        assert flag not in output


class TestSSHConfig:
    def test_lxconfigs(self, ix, lxc_setup):
        d = ix.lxconfigs_dir
        assert d.name == "lxconfigs"
        assert d.exists()
        path = ix.ssh_config_path
        assert path.name == "ssh-config"
        assert path.parent.name == "lxconfigs"

    def test_write_ssh_config(self, ix, lxc_setup):
        path = ix.write_ssh_config()
        assert path.exists()
        text = path.read_text()

        for c in lxc_setup:
            if c.get("ip"):
                assert c["name"] in text
                assert f"Hostname {c['ip']}" in text

        assert "User root" in text
        assert "IdentityFile" in text
        assert "StrictHostKeyChecking accept-new" in text


def test_dns(ix, relay_container):
    def dig(qname, qtype):
        ct = ix.get_dns_container()
        return ct.bash(f"dig @127.0.0.1 {qname} {qtype} +short").strip()

    domain = relay_container["domain"]
    assert dig(domain, "A") == relay_container["ip"]
    assert domain in dig(domain, "MX")
    assert "587" in dig(f"_submission._tcp.{domain}", "SRV")


class TestLxcStatus:
    def test_cli_lxc_status_help(self, cmdeploy):
        result = cmdeploy("lxc-status", "--help")
        assert result.returncode == 0
        assert "status" in result.stdout.lower()

    def test_shows_containers(self, lxc_setup, capsys):

        class QuietOut:
            def red(self, msg, **kw):
                pass

            def green(self, msg, **kw):
                pass

        ret = cli.lxc_status_cmd(None, QuietOut())
        assert ret == 0
        captured = capsys.readouterr().out
        assert "ns-localchat" in captured
        assert "running" in captured

    def test_deploy_freshness(self, ix, monkeypatch):

        ct = ix.get_container("x")

        monkeypatch.setattr(
            "cmdeploy.lxc.incus.RelayContainer.deployed_version",
            lambda _self: "abc123def456",
        )
        monkeypatch.setattr(
            "cmdeploy.lxc.incus.RelayContainer.deployed_domain",
            lambda _self: ct.domain,
        )
        monkeypatch.setattr(
            "cmdeploy.lxc.cli.get_version_string",
            lambda: "abc123def456",
        )
        assert "IN-SYNC" in cli._deploy_status(ct, "abc123def456", ix)
        assert "STALE" in cli._deploy_status(ct, "other_hash_here", ix)

        # Hash matches but local has uncommitted changes
        monkeypatch.setattr(
            "cmdeploy.lxc.cli.get_version_string",
            lambda: "abc123def456\ndiff --git a/foo",
        )
        assert "DIRTY" in cli._deploy_status(ct, "abc123def456", ix)

        monkeypatch.setattr(
            "cmdeploy.lxc.incus.RelayContainer.deployed_version",
            lambda _self: None,
        )
        assert "NOT DEPLOYED" in cli._deploy_status(ct, "abc123", ix)
