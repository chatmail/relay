from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from pyinfra.facts.deb import DebPackages

from cmdeploy.dovecot import deployer as dovecot_deployer


def make_host(*fact_pairs):
    """Build a mock host; get_fact(cls) dispatches to the provided facts mapping.

    Args:
        *fact_pairs: tuples of (fact_class, fact_value) to register

    Returns:
        SimpleNamespace with get_fact that raises a clear error if an
        unexpected fact type is requested.
    """
    facts = dict(fact_pairs)

    def get_fact(cls):
        if cls not in facts:
            registered = ", ".join(c.__name__ for c in facts)
            raise LookupError(
                f"unexpected get_fact({cls.__name__}); only registered: {registered}"
            )
        return facts[cls]

    return SimpleNamespace(get_fact=get_fact)


@pytest.fixture
def deployer():
    return dovecot_deployer.DovecotDeployer(
        SimpleNamespace(mail_domain="chat.example.org"),
        disable_mail=False,
    )


@pytest.fixture
def patch_blocked(monkeypatch):
    monkeypatch.setattr(dovecot_deployer, "blocked_service_startup", nullcontext)


@pytest.fixture
def mock_files_put(monkeypatch):
    monkeypatch.setattr(
        dovecot_deployer.files,
        "put",
        lambda **kwargs: SimpleNamespace(changed=False),
    )


@pytest.fixture
def track_shell(monkeypatch):
    calls = []
    monkeypatch.setattr(
        dovecot_deployer.server,
        "shell",
        lambda **kwargs: calls.append(kwargs) or SimpleNamespace(changed=False),
    )
    return calls


def test_download_dovecot_package_skips_epoch_matched_install(monkeypatch):
    epoch_version = dovecot_deployer.DOVECOT_PACKAGE_VERSION
    downloads = []
    monkeypatch.setattr(
        dovecot_deployer,
        "host",
        make_host((DebPackages, {"dovecot-core": [epoch_version]})),
    )
    monkeypatch.setattr(
        dovecot_deployer,
        "_pick_url",
        lambda primary, fallback: primary,
    )
    monkeypatch.setattr(
        dovecot_deployer.files,
        "download",
        lambda **kwargs: downloads.append(kwargs),
    )

    deb, changed = dovecot_deployer._download_dovecot_package("core", "amd64")

    assert deb is None, f"expected no deb path when version matches, got {deb!r}"
    assert changed is False, "should not flag changed when version already installed"
    assert downloads == [], "should not download when version already installed"


def test_download_dovecot_package_uses_archive_version_for_url_and_filename(
    monkeypatch,
):
    downloads = []
    monkeypatch.setattr(
        dovecot_deployer,
        "host",
        make_host((DebPackages, {})),
    )
    monkeypatch.setattr(
        dovecot_deployer,
        "_pick_url",
        lambda primary, fallback: primary,
    )
    monkeypatch.setattr(
        dovecot_deployer.files,
        "download",
        lambda **kwargs: downloads.append(kwargs),
    )

    deb, changed = dovecot_deployer._download_dovecot_package("core", "amd64")

    archive_version = dovecot_deployer.DOVECOT_ARCHIVE_VERSION.replace("+", "%2B")
    expected_deb = f"/root/dovecot-core_{archive_version}_amd64.deb"

    # Verify the returned path uses archive version, not package version (with epoch)
    assert changed is True, "should flag changed when package not yet installed"
    assert deb == expected_deb, f"deb path mismatch: {deb!r} != {expected_deb!r}"
    assert dovecot_deployer.DOVECOT_PACKAGE_VERSION not in deb, (
        f"deb path should use archive version (no epoch), got {deb!r}"
    )
    assert len(downloads) == 1, "files.download should be called exactly once"


def test_install_skips_dpkg_path_when_epoch_matched_packages_present(
    deployer, patch_blocked, mock_files_put, track_shell, monkeypatch
):
    monkeypatch.setattr(
        dovecot_deployer,
        "host",
        make_host(
            (
                dovecot_deployer.DebPackages,
                {
                    "dovecot-core": [dovecot_deployer.DOVECOT_PACKAGE_VERSION],
                    "dovecot-imapd": [dovecot_deployer.DOVECOT_PACKAGE_VERSION],
                    "dovecot-lmtpd": [dovecot_deployer.DOVECOT_PACKAGE_VERSION],
                },
            ),
            (dovecot_deployer.Arch, "x86_64"),
        ),
    )
    downloads = []
    monkeypatch.setattr(
        dovecot_deployer.files,
        "download",
        lambda **kwargs: downloads.append(kwargs),
    )

    deployer.install()

    assert downloads == [], "should not download when all packages epoch-matched"
    assert track_shell == [], "should not run dpkg when all packages epoch-matched"
    assert deployer.need_restart is False, (
        "need_restart should be False when nothing changed"
    )


def test_install_unsupported_arch_falls_back_to_apt(
    deployer, patch_blocked, mock_files_put, track_shell, monkeypatch
):
    # For unsupported architectures, all fact lookups return the arch string.
    monkeypatch.setattr(
        dovecot_deployer,
        "host",
        SimpleNamespace(get_fact=lambda cls: "riscv64"),
    )
    apt_calls = []

    # Mirrors apt.packages() return value: OperationMeta with .changed property.
    # Only lmtpd triggers a change to verify |= accumulation of changed flags.
    def fake_apt(**kwargs):
        apt_calls.append(kwargs)
        changed = "lmtpd" in kwargs["packages"][0]
        return SimpleNamespace(changed=changed)

    monkeypatch.setattr(dovecot_deployer.apt, "packages", fake_apt)

    deployer.install()

    actual_pkgs = [c["packages"] for c in apt_calls]
    assert actual_pkgs == [["dovecot-core"], ["dovecot-imapd"], ["dovecot-lmtpd"]], (
        f"expected apt install of core/imapd/lmtpd, got {actual_pkgs}"
    )
    assert track_shell == [], "should not run dpkg for unsupported arch"
    assert deployer.need_restart is True, (
        "need_restart should be True when apt installed a package"
    )


def test_install_runs_dpkg_when_packages_need_download(
    deployer, patch_blocked, mock_files_put, track_shell, monkeypatch
):
    monkeypatch.setattr(
        dovecot_deployer,
        "host",
        make_host(
            (dovecot_deployer.DebPackages, {}),
            (dovecot_deployer.Arch, "x86_64"),
        ),
    )
    monkeypatch.setattr(
        dovecot_deployer,
        "_pick_url",
        lambda primary, fallback: primary,
    )
    monkeypatch.setattr(
        dovecot_deployer.files,
        "download",
        lambda **kwargs: SimpleNamespace(changed=True),
    )

    deployer.install()

    assert len(track_shell) == 1, (
        f"expected one server.shell() call for dpkg install, got {len(track_shell)}"
    )
    cmds = track_shell[0]["commands"]
    assert len(cmds) == 3, f"expected 3 dpkg/apt commands, got: {cmds}"
    assert cmds[0].startswith("dpkg --force-confdef --force-confold -i ")
    assert "apt-get -y --fix-broken install" in cmds[1]
    assert cmds[2].startswith("dpkg --force-confdef --force-confold -i ")
    assert deployer.need_restart is True, (
        "need_restart should be True after dpkg install"
    )


def test_pick_url_falls_back_on_primary_error(monkeypatch):
    def raise_error(req, timeout):
        raise OSError("connection timeout")

    monkeypatch.setattr(dovecot_deployer.urllib.request, "urlopen", raise_error)
    result = dovecot_deployer._pick_url("http://primary", "http://fallback")
    assert result == "http://fallback", (
        f"should fall back when primary fails, got {result!r}"
    )
