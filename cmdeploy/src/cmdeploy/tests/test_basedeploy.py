from unittest.mock import MagicMock, patch

from cmdeploy.basedeploy import Deployer


def test_put_file_restart_and_reload():
    deployer = Deployer()
    mock_res = MagicMock()
    mock_res.changed = True

    with patch("cmdeploy.basedeploy.files.put", return_value=mock_res):
        # 1. Test regular file
        deployer.put_file("foo.conf", "/etc/foo.conf")
        assert deployer.need_restart is True
        assert deployer.daemon_reload is False

        # Reset state
        deployer.need_restart = False

        # 2. Test systemd unit
        deployer.put_file("test.service", "/etc/systemd/system/test.service")
        assert deployer.need_restart is True
        assert deployer.daemon_reload is True


def test_put_template_restart_and_reload():
    deployer = Deployer()
    mock_res = MagicMock()
    mock_res.changed = True

    with patch("cmdeploy.basedeploy.files.template", return_value=mock_res):
        # 1. Test regular file
        deployer.put_template("foo.j2", "/etc/foo.conf")
        assert deployer.need_restart is True
        assert deployer.daemon_reload is False

        # Reset state
        deployer.need_restart = False

        # 2. Test systemd unit
        deployer.put_template("test.service.j2", "/etc/systemd/system/test.service")
        assert deployer.need_restart is True
        assert deployer.daemon_reload is True


def test_no_change_no_restart():
    deployer = Deployer()
    mock_res = MagicMock()
    mock_res.changed = False

    with patch("cmdeploy.basedeploy.files.put", return_value=mock_res):
        deployer.put_file("foo.conf", "/etc/systemd/system/foo.service")
        assert deployer.need_restart is False
        assert deployer.daemon_reload is False


def test_put_file_disabled():
    deployer = Deployer()
    deployer.enabled = False
    mock_res = MagicMock()
    mock_res.changed = True

    with patch("cmdeploy.basedeploy.files.file", return_value=mock_res) as mock_file:
        deployer.put_file("foo.conf", "/etc/foo.conf")
        mock_file.assert_called_once_with(
            name="Remove /etc/foo.conf", path="/etc/foo.conf", present=False
        )
        assert deployer.need_restart is True
        assert deployer.daemon_reload is False

        # Reset state
        deployer.need_restart = False
        mock_file.reset_mock()

        deployer.put_file("test.service", "/etc/systemd/system/test.service")
        mock_file.assert_called_once_with(
            name="Remove /etc/systemd/system/test.service",
            path="/etc/systemd/system/test.service",
            present=False,
        )
        assert deployer.need_restart is True
        assert deployer.daemon_reload is True


def test_put_template_disabled():
    deployer = Deployer()
    deployer.enabled = False
    mock_res = MagicMock()
    mock_res.changed = True

    with patch("cmdeploy.basedeploy.files.file", return_value=mock_res) as mock_file:
        deployer.put_template("foo.j2", "/etc/foo.conf")
        mock_file.assert_called_once_with(
            name="Remove /etc/foo.conf", path="/etc/foo.conf", present=False
        )
        assert deployer.need_restart is True
        assert deployer.daemon_reload is False

        # Reset state
        deployer.need_restart = False

        # Test systemd unit removal
        mock_file.reset_mock()
        deployer.put_template("test.service.j2", "/etc/systemd/system/test.service")
        mock_file.assert_called_once_with(
            name="Remove /etc/systemd/system/test.service",
            path="/etc/systemd/system/test.service",
            present=False,
        )
        assert deployer.need_restart is True
        assert deployer.daemon_reload is True


def test_remove_file():
    deployer = Deployer()
    mock_res = MagicMock()
    mock_res.changed = True

    with patch("cmdeploy.basedeploy.files.file", return_value=mock_res) as mock_file:
        # Regular file removal
        deployer.remove_file("/etc/foo.conf")
        mock_file.assert_called_once_with(
            name="Remove /etc/foo.conf", path="/etc/foo.conf", present=False
        )
        assert deployer.need_restart is True
        assert deployer.daemon_reload is False

        # Reset state
        deployer.need_restart = False

        # Systemd unit removal
        mock_file.reset_mock()
        deployer.remove_file("/etc/systemd/system/test.service")
        mock_file.assert_called_once_with(
            name="Remove /etc/systemd/system/test.service",
            path="/etc/systemd/system/test.service",
            present=False,
        )
        assert deployer.need_restart is True
        assert deployer.daemon_reload is True


def test_ensure_line():
    deployer = Deployer()
    mock_res = MagicMock()
    mock_res.changed = True

    with patch("cmdeploy.basedeploy.files.line", return_value=mock_res) as mock_line:
        # Regular file line
        deployer.ensure_line("test line", "/etc/foo.conf", "MY_LINE=1")
        mock_line.assert_called_once_with(
            name="test line", path="/etc/foo.conf", line="MY_LINE=1"
        )
        assert deployer.need_restart is True
        assert deployer.daemon_reload is False

        # Reset state
        deployer.need_restart = False

        # Systemd unit file line (unlikely but possible)
        mock_line.reset_mock()
        deployer.ensure_line("test line", "/etc/systemd/system/test.service", "MY_LINE=1")
        assert deployer.need_restart is True
        assert deployer.daemon_reload is True


def test_untracked_changes():
    deployer = Deployer()
    mock_res = MagicMock()
    mock_res.changed = True

    with patch("cmdeploy.basedeploy.files.put", return_value=mock_res):
        deployer.put_file("foo.conf", "/etc/foo.conf")
        assert deployer.need_restart is False
        assert deployer.daemon_reload is False

    with patch("cmdeploy.basedeploy.files.template", return_value=mock_res):
        deployer.put_template("foo.j2", "/etc/foo.conf")
        assert deployer.need_restart is False
        assert deployer.daemon_reload is False

    with patch("cmdeploy.basedeploy.files.file", return_value=mock_res):
        deployer.remove_file("/etc/foo.conf")
        assert deployer.need_restart is False
        assert deployer.daemon_reload is False

    with patch("cmdeploy.basedeploy.files.line", return_value=mock_res):
        deployer.ensure_line("test", "/etc/foo.conf", "LINE")
        assert deployer.need_restart is False
        assert deployer.daemon_reload is False
