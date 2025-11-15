import importlib.resources
import io
import os

from pyinfra.operations import files, server, systemd


def get_resource(arg, pkg=__package__):
    return importlib.resources.files(pkg).joinpath(arg)


def configure_remote_units(mail_domain, units) -> None:
    remote_base_dir = "/usr/local/lib/chatmaild"
    remote_venv_dir = f"{remote_base_dir}/venv"
    remote_chatmail_inipath = f"{remote_base_dir}/chatmail.ini"
    root_owned = dict(user="root", group="root", mode="644")

    # install systemd units
    for fn in units:
        execpath = fn if fn != "filtermail-incoming" else "filtermail"
        params = dict(
            execpath=f"{remote_venv_dir}/bin/{execpath}",
            config_path=remote_chatmail_inipath,
            remote_venv_dir=remote_venv_dir,
            mail_domain=mail_domain,
        )

        basename = fn if "." in fn else f"{fn}.service"

        source_path = get_resource(f"service/{basename}.f")
        content = source_path.read_text().format(**params).encode()

        files.put(
            name=f"Upload {basename}",
            src=io.BytesIO(content),
            dest=f"/etc/systemd/system/{basename}",
            **root_owned,
        )


def activate_remote_units(units) -> None:
    # activate systemd units
    for fn in units:
        basename = fn if "." in fn else f"{fn}.service"

        if fn == "chatmail-expire" or fn == "chatmail-fsreport":
            # don't auto-start but let the corresponding timer trigger execution
            enabled = False
        else:
            enabled = True
        systemd.service(
            name=f"Setup {basename}",
            service=basename,
            running=enabled,
            enabled=enabled,
            restarted=enabled,
            daemon_reload=True,
        )


class Deployment:
    def install(self, deployer):
        # optional 'required_users' contains a list of (user, group, secondary-group-list) tuples.
        # If the group is None, no group is created corresponding to that user.
        # If the secondary group list is not None, all listed groups are created as well.
        required_users = getattr(deployer, "required_users", [])
        for user, group, groups in required_users:
            if group is not None:
                server.group(
                    name="Create {} group".format(group), group=group, system=True
                )
            if groups is not None:
                for group2 in groups:
                    server.group(
                        name="Create {} group".format(group2), group=group2, system=True
                    )
            server.user(
                name="Create {} user".format(user),
                user=user,
                group=group,
                groups=groups,
                system=True,
            )

        deployer.install()

    def configure(self, deployer):
        deployer.configure()

    def activate(self, deployer):
        deployer.activate()

    def perform_stages(self, deployers):
        default_stages = "install,configure,activate"
        stages = os.getenv("CMDEPLOY_STAGES", default_stages).split(",")

        for stage in stages:
            for deployer in deployers:
                getattr(self, stage)(deployer)


class Deployer:
    need_restart = False

    def install(self):
        pass

    def configure(self):
        pass

    def activate(self):
        pass
