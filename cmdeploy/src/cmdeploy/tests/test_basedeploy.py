from unittest.mock import MagicMock, patch

from cmdeploy.basedeploy import Deployer


def test_put_file_restart_and_reload():
    deployer = Deployer()
    mock_res = MagicMock()
    mock_res.changed = True

    with patch("cmdeploy.basedeploy.files.put", return_value=mock_res):
        deployer.put_file("foo.conf", "/etc/foo.conf")
        assert deployer.need_restart is True
        assert deployer.daemon_reload is False

        deployer.need_restart = False

        deployer.put_file("test.service", "/etc/systemd/system/test.service")
        assert deployer.need_restart is True
        assert deployer.daemon_reload is True


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


def test_ensure_systemd_unit():
    deployer = Deployer()
    mock_res = MagicMock()
    mock_res.changed = True

    # Plain service file
    with patch("cmdeploy.basedeploy.files.put", return_value=mock_res) as mock_put:
        deployer.ensure_systemd_unit("iroh-relay.service")
        assert (
            mock_put.call_args.kwargs["dest"]
            == "/etc/systemd/system/iroh-relay.service"
        )
        assert deployer.need_restart is True
        assert deployer.daemon_reload is True

    deployer.need_restart = False
    deployer.daemon_reload = False

    # Template (.j2) dispatches to put_template and strips .j2 suffix
    with patch("cmdeploy.basedeploy.files.template", return_value=mock_res) as mock_tpl:
        deployer.ensure_systemd_unit(
            "filtermail/chatmaild.service.j2",
            bin_path="/usr/local/bin/filtermail",
        )
        assert (
            mock_tpl.call_args.kwargs["dest"] == "/etc/systemd/system/chatmaild.service"
        )

    deployer.need_restart = False
    deployer.daemon_reload = False

    # Explicit dest_name override
    with patch("cmdeploy.basedeploy.files.put", return_value=mock_res) as mock_put:
        deployer.ensure_systemd_unit(
            "acmetool/acmetool-reconcile.timer",
            dest_name="acmetool-reconcile.timer",
        )
        assert (
            mock_put.call_args.kwargs["dest"]
            == "/etc/systemd/system/acmetool-reconcile.timer"
        )


def test_ensure_service():
    deployer = Deployer()

    with patch("cmdeploy.basedeploy.systemd.service") as mock_svc:
        deployer.need_restart = True
        deployer.daemon_reload = True
        deployer.ensure_service("nginx.service")
        mock_svc.assert_called_once_with(
            name="Start and enable nginx.service",
            service="nginx.service",
            running=True,
            enabled=True,
            restarted=True,
            daemon_reload=True,
        )
        # Flags must be reset after the call
        assert deployer.need_restart is False
        assert deployer.daemon_reload is False

    with patch("cmdeploy.basedeploy.systemd.service") as mock_svc:
        # Stopping suppresses restarted even when need_restart is True
        deployer.need_restart = True
        deployer.daemon_reload = True
        deployer.ensure_service(
            "mta-sts-daemon.service",
            running=False,
            enabled=False,
        )
        assert mock_svc.call_args.kwargs["restarted"] is False
        assert deployer.need_restart is False

    with patch("cmdeploy.basedeploy.systemd.service") as mock_svc:
        # Multiple calls: flags reset after the first
        deployer.need_restart = True
        deployer.daemon_reload = True
        deployer.ensure_service("chatmaild.service")
        deployer.ensure_service("chatmaild-metadata.service")
        second_call = mock_svc.call_args_list[1]
        assert second_call.kwargs["restarted"] is False
        assert second_call.kwargs["daemon_reload"] is False
