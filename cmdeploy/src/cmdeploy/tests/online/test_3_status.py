import os

from cmdeploy.cmdeploy import main


def test_status_cmd(chatmail_config, capsys, request):
    os.chdir(request.config.invocation_params.dir)
    command = ["status"]
    if os.getenv("CHATMAIL_SSH"):
        command.append("--ssh-host")
        command.append(os.getenv("CHATMAIL_SSH"))
    assert main(command) == 0
    status_out = capsys.readouterr()
    print(status_out.out)

    assert len(status_out.out.splitlines()) > 5

    """
    don't test actual server state:

    services = [
        "acmetool-redirector",
        "chatmail-metadata",
        "doveauth",
        "dovecot",
        "fcgiwrap",
        "filtermail-incoming",
        "filtermail",
        "lastlogin",
        "nginx",
        "opendkim",
        "postfix@-",
        "systemd-journald",
        "turnserver",
        "unbound",
    ]
    not_running = []
    for service in services:
        active = False
        for line in status_out:
            if service in line:
                active = True
                if not "loaded" in line:
                    active = False
                if not "active" in line:
                    active = False
                if not "running" in line:
                    active = False
                break
        if not active:
            not_running.append(service)
    assert not_running == []
    """
