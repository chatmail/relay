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

        deployer = Deployer()

        deployer.put_file("test.service", "/etc/systemd/system/test.service")
        assert deployer.need_restart is True
        assert deployer.daemon_reload is True


def test_remove_file():
    deployer = Deployer()
    mock_res = MagicMock()
    mock_res.changed = True

    with patch("cmdeploy.basedeploy.files.file", return_value=mock_res) as mock_file:
        deployer.remove_file("/etc/foo.conf")
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

    deployer = Deployer()

    # Template (.j2) dispatches to put_template and strips .j2 suffix
    with patch("cmdeploy.basedeploy.files.template", return_value=mock_res) as mock_tpl:
        deployer.ensure_systemd_unit(
            "filtermail/chatmaild.service.j2",
            bin_path="/usr/local/bin/filtermail",
        )
        assert (
            mock_tpl.call_args.kwargs["dest"] == "/etc/systemd/system/chatmaild.service"
        )

    deployer = Deployer()

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
    with patch("cmdeploy.basedeploy.systemd.service") as mock_svc:
        deployer = Deployer()
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
        # daemon_reload is cleared to avoid multiple systemctl daemon-reload calls
        # need_restart is kept to ensure all subsequent services also restart
        assert deployer.need_restart is True
        assert deployer.daemon_reload is False

    with patch("cmdeploy.basedeploy.systemd.service") as mock_svc:
        # Stopping suppresses restarted even when need_restart is True
        deployer = Deployer()
        deployer.need_restart = True
        deployer.daemon_reload = True
        deployer.ensure_service(
            "mta-sts-daemon.service",
            running=False,
            enabled=False,
        )
        assert mock_svc.call_args.kwargs["restarted"] is False
        assert deployer.need_restart is True

    with patch("cmdeploy.basedeploy.systemd.service") as mock_svc:
        # Multiple calls: daemon_reload resets after first, need_restart persists
        deployer = Deployer()
        deployer.need_restart = True
        deployer.daemon_reload = True
        deployer.ensure_service("chatmaild.service")
        deployer.ensure_service("chatmaild-metadata.service")
        second_call = mock_svc.call_args_list[1]
        assert second_call.kwargs["restarted"] is True
        assert second_call.kwargs["daemon_reload"] is False
