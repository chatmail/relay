import importlib.resources
import io
import os

from pyinfra.operations import files, server, systemd


def has_systemd():
    """Returns False during Docker image builds or any other non-systemd environment."""
    return os.path.isdir("/run/systemd/system")


def get_resource(arg, pkg=__package__):
    return importlib.resources.files(pkg).joinpath(arg)


def configure_remote_units(mail_domain, units) -> None:
    remote_base_dir = "/usr/local/lib/chatmaild"
    remote_venv_dir = f"{remote_base_dir}/venv"
    remote_chatmail_inipath = f"{remote_base_dir}/chatmail.ini"
    root_owned = dict(user="root", group="root", mode="644")

    # install systemd units
    for fn in units:
        params = dict(
            execpath=f"{remote_venv_dir}/bin/{fn}",
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
    """Base class for deployers that manage remote service configuration.

    Deployers go through three stages: ``install``, ``configure``, and
    ``activate``.  During ``configure``, use :meth:`put_file` and
    :meth:`put_template` to upload files — they automatically set
    ``need_restart = True`` when a file changes on the remote host.
    The ``activate`` stage can then inspect ``need_restart`` to decide
    whether to restart or reload the managed service.

    Deployers with an ``enabled`` flag (default ``True``) support a
    disabled mode: when ``enabled`` is ``False``, the ``put_*`` methods
    remove the target file from the remote host instead of uploading it,
    allowing clean un-deployment of optional components.
    """

    enabled = True
    need_restart = False
    daemon_reload = False

    def install(self):
        pass

    def configure(self):
        pass

    def activate(self):
        pass

    def put_file(
        self, *, name, dest, src=None, executable=False, owner="root"
    ):
        """Upload a file to *dest*, or remove it when the deployer is disabled.

        Sets ``need_restart = True`` when the remote file changes.
        When ``self.enabled`` is ``False``, the file at *dest* is removed
        instead of uploaded.
        """
        if self.enabled:
            mode = "755" if executable else "644"
            res = files.put(
                name=name, src=src, dest=dest, user=owner, group=owner, mode=mode
            )
        else:
            res = files.file(name=name, path=dest, present=False)

        if res.changed:
            self.need_restart = True
        return res

    def put_template(
        self, *, name, src, dest, owner="root", mode="644", **kwargs
    ):
        """Upload a Jinja2 template to *dest*, or remove it when disabled.

        Sets ``need_restart = True`` when the rendered remote file changes.
        When ``self.enabled`` is ``False``, the file at *dest* is removed
        instead of uploaded.  Extra *kwargs* are passed to the template
        as render context.
        """
        if self.enabled:
            res = files.template(
                name=name,
                src=src,
                dest=dest,
                user=owner,
                group=owner,
                mode=mode,
                **kwargs,
            )
        else:
            res = files.file(name=name, path=dest, present=False)

        if res.changed:
            self.need_restart = True
        return res
