import shutil

import psutil

from chatmaild.syslimits import has_sufficient_resources

PERMISSIVE = {
    "max_load_1m": "99999",
    "min_available_memory": "0",
    "min_free_disk_space": "0",
}


def test_rejects_constrained_system(make_config, caplog):
    assert has_sufficient_resources(make_config("chat.example.org", PERMISSIVE))
    for settings in (
        {"max_load_1m": "-1.0"},
        {"min_available_memory": "99999999G"},
        {"min_free_disk_space": "99999999G"},
    ):
        config = make_config("chat.example.org", PERMISSIVE | settings)
        caplog.clear()
        assert not has_sufficient_resources(config), settings
        assert "registration rejected" in caplog.text


def test_unreadable_disk_does_not_reject(make_config, caplog):
    config = make_config(
        "chat.example.org", PERMISSIVE | {"min_free_disk_space": "99999999G"}
    )
    shutil.rmtree(config.mailboxes_dir)
    assert has_sufficient_resources(config)
    assert "ignoring" in caplog.text


def test_one_unreadable_value_keeps_other_checks(make_config, monkeypatch, caplog):
    def raise_error(*args):
        raise psutil.Error("dud")

    monkeypatch.setattr(psutil, "getloadavg", raise_error)
    config = make_config(
        "chat.example.org", PERMISSIVE | {"min_free_disk_space": "99999999G"}
    )
    assert not has_sufficient_resources(config)
    assert "ignoring" in caplog.text
