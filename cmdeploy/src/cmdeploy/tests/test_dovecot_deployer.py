from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from pyinfra.facts.deb import DebPackages
from pyinfra.facts.server import Command

from cmdeploy.dovecot import deployer as dovecot_deployer


def _fact_name(key):
    if isinstance(key, tuple):
        return f"{key[0].__name__}{key[1:]!r}"
    return key.__name__


def make_host(*fact_pairs):
    """Build a mock host; get_fact() dispatches to the provided facts mapping.

    Args:
        *fact_pairs: (fact_class, value) to match any call of that fact, or
            ((fact_class, *args), value) to match one specific call. Needed
            for Command, which install() and check_restart() invoke with
            different scripts; a bare Command entry would serve both.

    Returns:
        SimpleNamespace with get_fact that raises a clear error if an
        unregistered fact is requested.
    """
    facts = dict(fact_pairs)

    def get_fact(cls, *args):
        for key in ((cls, *args), cls):
            if key in facts:
                return facts[key]
        registered = ", ".join(_fact_name(k) for k in facts)
        raise LookupError(
            f"unexpected get_fact({_fact_name((cls, *args))}); only registered: {registered}"
        )

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
    # what dpkg reports after installing our deb: epoch + the +debNu1 suffix
    # that chatmail/dovecot CI stamps via dch before building
    epoch_version = f"1:{dovecot_deployer._stamped_version(12)}"
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

    deb, changed = dovecot_deployer._download_dovecot_package("core", "amd64", deb_release=12)

    assert deb is None, f"expected no deb path when version matches, got {deb!r}"
    assert changed is False, "should not flag changed when version already installed"
    assert downloads == [], "should not download when version already installed"


@pytest.mark.parametrize("deb_release", [12, 13])
@pytest.mark.parametrize("arch", ["amd64", "arm64"])
def test_download_dovecot_package_uses_archive_version_for_url_and_filename(
    monkeypatch, deb_release, arch
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

    deb, changed = dovecot_deployer._download_dovecot_package(
        "core", arch, deb_release=deb_release
    )

    stamped = dovecot_deployer._stamped_version(deb_release)
    expected_deb = f"/root/dovecot-core_{stamped}_{arch}.deb"

    # path uses the stamped version, and deb filenames never carry the epoch
    assert changed is True, "should flag changed when package not yet installed"
    assert deb == expected_deb, f"deb path mismatch: {deb!r} != {expected_deb!r}"
    assert "1:" not in deb, f"deb filename must not contain the epoch, got {deb!r}"
    assert len(downloads) == 1, "files.download should be called exactly once"
    # the checksum is the security boundary: verify the right table row is used
    assert (
        downloads[0]["sha256sum"]
        == dovecot_deployer.DOVECOT_SHA256[(arch, deb_release, "core")]
    ), "must pass the sha256 matching (arch, release, package)"
    assert f"deb{deb_release}u1" in downloads[0]["src"], (
        f"download URL should carry the deb{deb_release} suffix, got {downloads[0]['src']!r}"
    )


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
                    "dovecot-core": [f"1:{dovecot_deployer._stamped_version(12)}"],
                    "dovecot-imapd": [f"1:{dovecot_deployer._stamped_version(12)}"],
                    "dovecot-lmtpd": [f"1:{dovecot_deployer._stamped_version(12)}"],
                    "dovecot-auth-lua": [f"1:{dovecot_deployer._stamped_version(12)}"],
                },
            ),
            (dovecot_deployer.Arch, "x86_64"),
            ((Command, dovecot_deployer.VERSION_ID_CMD), 'VERSION_ID="12"'),
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
    assert deployer.need_restart is False, "need_restart should be False when nothing changed"


def test_install_unsupported_arch_raises(
    deployer, patch_blocked, mock_files_put, track_shell, monkeypatch
):
    monkeypatch.setattr(
        dovecot_deployer,
        "host",
        make_host(
            (dovecot_deployer.Arch, "riscv64"),
            ((Command, dovecot_deployer.VERSION_ID_CMD), 'VERSION_ID="12"'),
        ),
    )

    # we never fall back to the pinned distro package
    with pytest.raises(ValueError, match="no dovecot build for dovecot-core"):
        deployer.install()

    assert track_shell == [], "should not run apt-get for unsupported arch"


def test_install_runs_dpkg_when_packages_need_download(
    deployer, patch_blocked, mock_files_put, track_shell, monkeypatch
):
    monkeypatch.setattr(
        dovecot_deployer,
        "host",
        make_host(
            (dovecot_deployer.DebPackages, {}),
            (dovecot_deployer.Arch, "x86_64"),
            ((Command, dovecot_deployer.VERSION_ID_CMD), 'VERSION_ID="12"'),
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

    assert len(track_shell) == 1, f"expected one server.shell() call for dpkg install, got {len(track_shell)}"
    cmds = track_shell[0]["commands"]
    assert len(cmds) == 1, f"expected single apt-get install command, got: {cmds}"
    assert "apt-get install -y" in cmds[0]
    assert '-o Dpkg::Options::="--force-confdef"' in cmds[0]
    assert '-o Dpkg::Options::="--force-confold"' in cmds[0]
    assert "--allow-downgrades" in cmds[0]
    assert ".deb" in cmds[0]
    assert deployer.need_restart is True, "need_restart should be True after dpkg install"


def test_pick_url_falls_back_on_primary_error(monkeypatch):
    def raise_error(req, timeout):
        raise OSError("connection timeout")

    monkeypatch.setattr(dovecot_deployer.urllib.request, "urlopen", raise_error)
    result = dovecot_deployer._pick_url("http://primary", "http://fallback")
    assert result == "http://fallback", f"should fall back when primary fails, got {result!r}"


def test_install_fails_on_unsupported_debian_version(deployer, patch_blocked, monkeypatch):
    monkeypatch.setattr(
        dovecot_deployer,
        "host",
        make_host(
            (dovecot_deployer.Arch, "x86_64"),
            ((Command, dovecot_deployer.VERSION_ID_CMD), 'VERSION_ID="99"'),
        ),
    )

    with pytest.raises(ValueError, match="no dovecot build for dovecot-core on deb99"):
        deployer.install()


@pytest.mark.parametrize(
    "version_line", ["", None, "ID=debian"], ids=["empty", "none", "no-version-id"]
)
def test_parse_version_id_raises_without_version_id(version_line):
    with pytest.raises(ValueError, match="cannot determine Debian release"):
        dovecot_deployer._parse_version_id(version_line)


@pytest.mark.parametrize("deb_release", [12, 13])
def test_parse_version_id(deb_release):
    parsed = dovecot_deployer._parse_version_id(f'VERSION_ID="{deb_release}"\n')
    assert parsed == deb_release


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
