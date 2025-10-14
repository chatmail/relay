import importlib
import os

import pytest

from cmdeploy.cmdeploy import get_parser, main
from cmdeploy.www import get_paths
import cmdeploy.remote.rshell
import cmdeploy.dns


@pytest.fixture(autouse=True)
def _chdir(tmp_path):
    old = os.getcwd()
    os.chdir(tmp_path)
    yield
    os.chdir(old)


class TestCmdline:
    def test_parser(self, capsys):
        parser = get_parser()
        parser.parse_args([])
        init = parser.parse_args(["init", "chat.example.org"])
        run = parser.parse_args(["run"])
        assert init and run

    def test_init_not_overwrite(self, capsys):
        assert main(["init", "chat.example.org"]) == 0
        capsys.readouterr()

        assert main(["init", "chat.example.org"]) == 1
        out, err = capsys.readouterr()
        assert "path exists" in out.lower()

        assert main(["init", "chat.example.org", "--force"]) == 0
        out, err = capsys.readouterr()
        assert "deleting config file" in out.lower()


def test_www_folder(example_config, tmp_path):
    reporoot = importlib.resources.files(__package__).joinpath("../../../../").resolve()
    assert not example_config.www_folder
    www_path, src_dir, build_dir = get_paths(example_config)
    assert www_path.absolute() == reporoot.joinpath("www").absolute()
    assert src_dir == reporoot.joinpath("www").joinpath("src")
    assert build_dir == reporoot.joinpath("www").joinpath("build")
    example_config.www_folder = "disabled"
    www_path, _, _ = get_paths(example_config)
    assert not www_path.is_dir()
    example_config.www_folder = str(tmp_path)
    www_path, src_dir, build_dir = get_paths(example_config)
    assert www_path == tmp_path
    assert not src_dir.exists()
    assert not build_dir
    src_path = tmp_path.joinpath("src")
    os.mkdir(src_path)
    with open(src_path / "index.md", "w") as f:
        f.write("# Test")
    www_path, src_dir, build_dir = get_paths(example_config)
    assert www_path == tmp_path
    assert src_dir == src_path
    assert build_dir == tmp_path.joinpath("build")


def test_dns_when_ssh_docker(monkeypatch):
    commands = []

    def shell(command, fail_ok=None, print=None):
        assert command == False
        commands.append(command)

    # mock shell function to add called commands to a global list
    monkeypatch.setattr(
        cmdeploy.remote.rshell, shell.__name__, shell
    )  # still doesn't get called in get_initial_remote_data :(
    print("test_cmdeploy: " + shell.__module__)
    # run cmdeploy dns with --ssh-host
    #   @docker
    cmdeploy.dns.get_initial_remote_data("@docker", "chatmail.example.org")
    for cmd in commands:
        print(cmd)
    #   localhost
    #   @local
    #   without --ssh-host
    # check which commands were called
    assert False
