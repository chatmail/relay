import importlib.resources

from pyinfra.operations import apt, files, server, systemd


def deploy_acmetool(email="", domains=[]):
    """Deploy acmetool."""
    apt.packages(
        name="Install acmetool",
        packages=["acmetool"],
    )

    files.file(
        name="Remove old acmetool cronjob, it is replaced with systemd timer.",
        path="/etc/cron.d/acmetool",
        present=False,
    )

    files.put(
        name="Install acmetool hook.",
        src=importlib.resources.files(__package__).joinpath("acmetool.hook").open("rb"),
        dest="/etc/acme/hooks/nginx",
        user="root",
        group="root",
        mode="744",
    )
    files.file(
        name="Remove acmetool hook from the wrong location where it was previously installed.",
        path="/usr/lib/acme/hooks/nginx",
        present=False,
    )

    files.template(
        src=importlib.resources.files(__package__).joinpath("response-file.yaml.j2"),
        dest="/var/lib/acme/conf/responses",
        user="root",
        group="root",
        mode="644",
        email=email,
    )

    files.template(
        src=importlib.resources.files(__package__).joinpath("target.yaml.j2"),
        dest="/var/lib/acme/conf/target",
        user="root",
        group="root",
        mode="644",
    )

    service_file = files.put(
        src=importlib.resources.files(__package__).joinpath(
            "acmetool-redirector.service"
        ),
        dest="/etc/systemd/system/acmetool-redirector.service",
        user="root",
        group="root",
        mode="644",
    )

    systemd.service(
        name="Setup acmetool-redirector service",
        service="acmetool-redirector.service",
        running=True,
        enabled=True,
        restarted=service_file.changed,
    )

    reconcile_service_file = files.put(
        src=importlib.resources.files(__package__).joinpath(
            "acmetool-reconcile.service"
        ),
        dest="/etc/systemd/system/acmetool-reconcile.service",
        user="root",
        group="root",
        mode="644",
    )

    systemd.service(
        name="Setup acmetool-reconcile service",
        service="acmetool-reconcile.service",
        running=False,
        enabled=False,
        daemon_reload=reconcile_service_file.changed,
    )

    reconcile_timer_file = files.put(
        src=importlib.resources.files(__package__).joinpath("acmetool-reconcile.timer"),
        dest="/etc/systemd/system/acmetool-reconcile.timer",
        user="root",
        group="root",
        mode="644",
    )

    systemd.service(
        name="Setup acmetool-reconcile timer",
        service="acmetool-reconcile.timer",
        running=True,
        enabled=True,
        daemon_reload=reconcile_timer_file.changed,
    )

    server.shell(
        name=f"Request certificate for: {', '.join(domains)}",
        commands=[f"acmetool want --xlog.severity=debug {' '.join(domains)}"],
    )
