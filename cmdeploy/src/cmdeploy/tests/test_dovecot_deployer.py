from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from pyinfra.facts.deb import DebPackages
from pyinfra.facts.server import Command

from cmdeploy.dovecot import deployer as dovecot_deployer

# what dpkg reports after installing our deb12 build
INSTALLED_DEB12 = f"1:{dovecot_deployer.DOVECOT_VERSION}+deb12u1"


def make_host(*fact_pairs):
    """Build a mock host; get_fact(cls) dispatches to the provided facts mapping.

    Args:
        *fact_pairs: tuples of (fact_class, fact_value) to register

    Returns:
        SimpleNamespace with get_fact that raises a clear error if an
        unexpected fact type is requested.
    """
    facts = dict(fact_pairs)

    def get_fact(cls, *args):
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
    epoch_version = INSTALLED_DEB12
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

    deb, changed = dovecot_deployer._download_dovecot_package(
        "core", "amd64", deb_release=12
    )

    assert deb is None, f"expected no deb path when version matches, got {deb!r}"
    assert changed is False, "should not flag changed when version already installed"
    assert downloads == [], "should not download when version already installed"


@pytest.mark.parametrize(("arch", "deb_release"), [("amd64", 12), ("arm64", 13)])
def test_download_dovecot_package_uses_archive_version_for_url_and_filename(
    monkeypatch, deb_release, arch
):
    downloads = []
    monkeypatch.setattr(
        dovecot_deployer,
        "host",
        make_host((DebPackages, {})),
    )
    urls = {}
    monkeypatch.setattr(
        dovecot_deployer,
        "_pick_url",
        lambda primary, fallback: urls.update(primary=primary, fallback=fallback)
        or primary,
    )
    monkeypatch.setattr(
        dovecot_deployer.files,
        "download",
        lambda **kwargs: downloads.append(kwargs),
    )

    deb, changed = dovecot_deployer._download_dovecot_package(
        "core", arch, deb_release=deb_release
    )

    version = dovecot_deployer.DOVECOT_VERSION
    deb_base = f"dovecot-core_{version}+deb{deb_release}u1_{arch}.deb"
    deb_base = deb_base.replace("+", "%2B")
    tag = version.replace("+", "%2B")

    # the release tag carries no distro suffix and filenames carry no epoch
    assert changed is True, "should flag changed when package not yet installed"
    assert deb == f"/root/{deb_base}"
    assert urls["primary"] == f"https://download.delta.chat/dovecot/{deb_base}"
    assert urls["fallback"] == (
        "https://github.com/chatmail/dovecot/releases/download/"
        f"upstream%2F{tag}/{deb_base}"
    )
    assert len(downloads) == 1, "files.download should be called exactly once"
    assert downloads[0]["src"] == urls["primary"]
    assert (
        downloads[0]["sha256sum"]
        == dovecot_deployer.DOVECOT_SHA256[(arch, deb_release, "core")]
    ), "must pass the sha256 matching (arch, release, package)"


def test_download_dovecot_package_replaces_deb12_build_after_upgrade_to_13(
    monkeypatch,
):
    downloads = []
    monkeypatch.setattr(
        dovecot_deployer,
        "host",
        make_host((DebPackages, {"dovecot-core": [INSTALLED_DEB12]})),
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

    deb, changed = dovecot_deployer._download_dovecot_package(
        "core", "amd64", deb_release=13
    )

    assert changed is True, "a deb12 build on a deb13 host must be replaced"
    assert "deb13u1" in deb, f"expected the deb13 build, got {deb!r}"
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
                    "dovecot-core": [INSTALLED_DEB12],
                    "dovecot-imapd": [INSTALLED_DEB12],
                    "dovecot-lmtpd": [INSTALLED_DEB12],
                    "dovecot-auth-lua": [INSTALLED_DEB12],
                },
            ),
            (dovecot_deployer.Arch, "x86_64"),
            (Command, 'VERSION_ID="12"'),
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


def test_install_unsupported_arch_raises(
    deployer, patch_blocked, mock_files_put, track_shell, monkeypatch
):
    monkeypatch.setattr(
        dovecot_deployer,
        "host",
        make_host(
            (dovecot_deployer.Arch, "riscv64"),
            (Command, 'VERSION_ID="12"'),
        ),
    )

    # we never fall back to the pinned distro package
    with pytest.raises(ValueError, match="no dovecot build for dovecot-core"):
        deployer.install()

    assert track_shell == [], "should not run dpkg for unsupported arch"


def test_install_runs_dpkg_when_packages_need_download(
    deployer, patch_blocked, mock_files_put, track_shell, monkeypatch
):
    monkeypatch.setattr(
        dovecot_deployer,
        "host",
        make_host(
            (dovecot_deployer.DebPackages, {}),
            (dovecot_deployer.Arch, "x86_64"),
            (Command, 'VERSION_ID="12"'),
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


def test_install_fails_on_unsupported_debian_version(
    deployer, patch_blocked, monkeypatch
):
    monkeypatch.setattr(
        dovecot_deployer,
        "host",
        make_host(
            (dovecot_deployer.Arch, "x86_64"),
            (Command, 'VERSION_ID="99"'),
        ),
    )

    with pytest.raises(ValueError, match="no dovecot build for dovecot-core on deb99"):
        deployer.install()


@pytest.mark.parametrize(
    "version_line",
    ["", None, "ID=debian", "VERSION_ID="],
    ids=["empty", "none", "no-version-id", "empty-value"],
)
def test_parse_version_id_raises_without_version_id(version_line):
    with pytest.raises(ValueError, match="cannot determine Debian release"):
        dovecot_deployer._parse_version_id(version_line)


@pytest.mark.parametrize(
    ("version_line", "deb_release"),
    [('VERSION_ID="12"\n', 12), ('VERSION_ID="13"\n', 13), ("VERSION_ID=13", 13)],
)
def test_parse_version_id(version_line, deb_release):
    assert dovecot_deployer._parse_version_id(version_line) == deb_release


def test_dovecot_sha256_covers_all_packages_per_release():
    """Every release in the table needs all four packages on both arches."""
    table = dovecot_deployer.DOVECOT_SHA256
    expected = {
        (arch, pkg)
        for arch in ("amd64", "arm64")
        for pkg in ("core", "imapd", "lmtpd", "auth-lua")
    }
    for release in {r for _, r, _ in table}:
        got = {(arch, pkg) for arch, r, pkg in table if r == release}
        assert got == expected, f"deb{release} incomplete: {sorted(expected - got)}"


def test_dovecot_sha256_has_no_duplicate_hashes():
    """Each build is a distinct file, so a repeated hash is a copy-paste error."""
    table = dovecot_deployer.DOVECOT_SHA256
    assert len(set(table.values())) == len(table)
