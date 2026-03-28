from contextlib import nullcontext
from types import SimpleNamespace

from cmdeploy.dovecot import deployer as dovecot_deployer


def make_deployer(disable_mail=False):
    return dovecot_deployer.DovecotDeployer(
        SimpleNamespace(mail_domain="chat.example.org"),
        disable_mail,
    )


def test_download_dovecot_package_skips_epoch_matched_install(monkeypatch):
    epoch_version = dovecot_deployer.DOVECOT_PACKAGE_VERSION
    downloads = []
    monkeypatch.setattr(
        dovecot_deployer,
        "host",
        SimpleNamespace(get_fact=lambda cls: {"dovecot-core": [epoch_version]}),
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

    assert deb is None
    assert changed is False
    assert downloads == []


def test_install_marks_package_changed_when_debs_present(monkeypatch):
    deployer = make_deployer()
    monkeypatch.setattr(dovecot_deployer, "blocked_service_startup", nullcontext)
    monkeypatch.setattr(
        dovecot_deployer,
        "host",
        SimpleNamespace(get_fact=lambda cls: "x86_64"),
    )
    monkeypatch.setattr(
        dovecot_deployer,
        "_download_dovecot_package",
        lambda package, arch: (f"/tmp/{package}.deb", False),
    )
    shell_calls = []
    monkeypatch.setattr(
        dovecot_deployer.server,
        "shell",
        lambda **kwargs: shell_calls.append(kwargs),
    )

    deployer.install()

    assert deployer.package_changed is True
    assert shell_calls


def test_install_skips_dpkg_path_when_epoch_matched_packages_present(monkeypatch):
    deployer = make_deployer()
    monkeypatch.setattr(dovecot_deployer, "blocked_service_startup", nullcontext)
    monkeypatch.setattr(
        dovecot_deployer,
        "host",
        SimpleNamespace(
            get_fact=lambda cls: {
                "dovecot-core": [dovecot_deployer.DOVECOT_PACKAGE_VERSION],
                "dovecot-imapd": [dovecot_deployer.DOVECOT_PACKAGE_VERSION],
                "dovecot-lmtpd": [dovecot_deployer.DOVECOT_PACKAGE_VERSION],
            }
            if cls is dovecot_deployer.DebPackages
            else "x86_64",
        ),
    )
    monkeypatch.setattr(
        dovecot_deployer,
        "_pick_url",
        lambda primary, fallback: primary,
    )
    downloads = []
    monkeypatch.setattr(
        dovecot_deployer.files,
        "download",
        lambda **kwargs: downloads.append(kwargs),
    )
    shell_calls = []
    monkeypatch.setattr(
        dovecot_deployer.server,
        "shell",
        lambda **kwargs: shell_calls.append(kwargs),
    )

    deployer.install()

    assert downloads == []
    assert shell_calls == []
    assert deployer.package_changed is False


def test_install_marks_package_changed_when_fallback_apt_installs(monkeypatch):
    deployer = make_deployer()
    monkeypatch.setattr(dovecot_deployer, "blocked_service_startup", nullcontext)
    monkeypatch.setattr(
        dovecot_deployer,
        "host",
        SimpleNamespace(get_fact=lambda cls: "riscv64"),
    )
    apt_calls = []
    monkeypatch.setattr(
        dovecot_deployer.apt,
        "packages",
        lambda **kwargs: apt_calls.append(kwargs) or SimpleNamespace(changed=True),
    )
    shell_calls = []
    monkeypatch.setattr(
        dovecot_deployer.server,
        "shell",
        lambda **kwargs: shell_calls.append(kwargs),
    )

    deployer.install()

    assert apt_calls
    assert shell_calls == []
    assert deployer.package_changed is True


def test_activate_restarts_on_package_change_without_config(monkeypatch):
    deployer = make_deployer()
    deployer.need_restart = False
    deployer.package_changed = True
    service_calls = []
    monkeypatch.setattr(dovecot_deployer, "activate_remote_units", lambda units: None)
    monkeypatch.setattr(
        dovecot_deployer.systemd,
        "service",
        lambda **kwargs: service_calls.append(kwargs),
    )

    deployer.activate()

    assert service_calls[0]["restarted"] is True
    assert deployer.need_restart is False
    assert deployer.package_changed is False


def test_activate_does_not_restart_when_mail_disabled(monkeypatch):
    deployer = make_deployer(disable_mail=True)
    deployer.need_restart = False
    deployer.package_changed = True
    service_calls = []
    monkeypatch.setattr(dovecot_deployer, "activate_remote_units", lambda units: None)
    monkeypatch.setattr(
        dovecot_deployer.systemd,
        "service",
        lambda **kwargs: service_calls.append(kwargs),
    )

    deployer.activate()

    assert service_calls[0]["restarted"] is False
    assert service_calls[0]["running"] is False
    assert service_calls[0]["enabled"] is False
    assert deployer.need_restart is False
    assert deployer.package_changed is False
