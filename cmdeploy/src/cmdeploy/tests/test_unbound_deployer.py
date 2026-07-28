from types import SimpleNamespace

from cmdeploy import deployers


def test_configure_relies_on_service_for_root_trust_anchor(monkeypatch):
    shell_calls = []
    monkeypatch.setattr(deployers.apt, "packages", lambda **kwargs: None)
    monkeypatch.setattr(
        deployers.server,
        "shell",
        lambda **kwargs: shell_calls.append(kwargs),
    )

    deployer = deployers.UnboundDeployer(SimpleNamespace(disable_ipv6=False))
    monkeypatch.setattr(deployer, "put_file", lambda *args, **kwargs: None)
    monkeypatch.setattr(deployer, "ensure_directory", lambda *args, **kwargs: None)
    monkeypatch.setattr(deployer, "put_template", lambda *args, **kwargs: None)

    deployer.configure()

    commands = [command for call in shell_calls for command in call["commands"]]
    assert not any("unbound-anchor" in command for command in commands)
