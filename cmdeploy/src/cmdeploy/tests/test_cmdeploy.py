import os

import pytest

from cmdeploy.cmdeploy import get_parser, main


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
