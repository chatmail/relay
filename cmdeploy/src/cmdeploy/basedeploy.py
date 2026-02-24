import importlib.resources
import io
import os

from pyinfra.operations import files, server, systemd


def has_systemd():
    """Returns False during Docker image builds or any other non-systemd environment."""
    return os.path.isdir("/run/systemd/system")


def get_resource(arg, pkg=__package__):
    return importlib.resources.files(pkg).joinpath(arg)


def configure_remote_units(mail_domain, units) -> bool:
    remote_base_dir = "/usr/local/lib/chatmaild"
    remote_venv_dir = f"{remote_base_dir}/venv"
    remote_chatmail_inipath = f"{remote_base_dir}/chatmail.ini"
    root_owned = dict(user="root", group="root", mode="644")
    changed = False

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

        res = files.put(
            name=f"Upload {basename}",
            src=io.BytesIO(content),
            dest=f"/etc/systemd/system/{basename}",
            **root_owned,
        )
        changed |= res.changed
    return changed


def activate_remote_units(units, daemon_reload=False) -> None:
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
            daemon_reload=daemon_reload,
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

    Deployers go through three stages: ``install``, ``configure``, and ``activate``.
    During ``configure``, use :meth:`put_file` and :meth:`put_template` to upload files.
    When a file changes on the remote host:
    - ``self.need_restart`` is set to ``True``, signaling that the managed service
      should be restarted during the ``activate`` stage.
    - ``self.daemon_reload`` is set to ``True`` if the file is a systemd unit or
      drop-in (detected via the ``/etc/systemd/system/`` prefix), signaling that
      a ``systemctl daemon-reload`` is required.

    Deployers with an ``enabled`` flag (default ``True``) support a disabled mode:
    when ``enabled`` is ``False``, the ``put_*`` methods remove the target file
    from the remote host instead of uploading it, allowing clean un-deployment of optional components.
    """

    def __init__(self):
        #: If True (default), :meth:`put_file` and :meth:`put_template` (the put helpers) will upload files.
        #: If False, they ensure the target file is removed.
        self.enabled = True
        #: Set to True if the remote service needs a restart.
        self.need_restart = False
        #: Set to True if systemd units/drop-ins changed and need a daemon-reload.
        self.daemon_reload = False

    def install(self):
        pass

    def configure(self):
        pass

    def activate(self):
        pass

    def put_file(self, src, dest, *, executable=False, owner="root", track=True):
        """Upload a file to *dest*, or remove it when the deployer is disabled.

        *src* may be a resource path string (resolved via :func:`get_resource`),
        a path-like, or a file-like object. Sets ``self.need_restart = True``
        when the dst file changes and *track* is True.
        """
        if isinstance(src, str):
            src = get_resource(src)
        verb = "Upload" if self.enabled else "Remove"
        name = f"{verb} {dest}"
        if self.enabled:
            mode = "755" if executable else "644"
            res = files.put(
                name=name, src=src, dest=dest, user=owner, group=owner, mode=mode
            )
        else:
            res = files.file(name=name, path=dest, present=False)

        return self._update_restart_signals(dest, res, track=track)

    def put_template(self, src, dest, *, owner="root", mode="644", track=True, **kwargs):
        """Upload a Jinja2 template to *dest*, or remove it when disabled.

        *src* may be a resource path string (resolved via :func:`get_resource`) or a path-like
        object. Sets ``need_restart = True`` when the dst file changes and *track* is True.
        Extra *kwargs* are passed as template render context.
        """
        if isinstance(src, str):
            src = get_resource(src)
        verb = "Upload" if self.enabled else "Remove"
        name = f"{verb} {dest}"
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

        return self._update_restart_signals(dest, res, track=track)

    def remove_file(self, dest, *, track=True):
        """Ensure *dest* is removed from the remote host.

        Sets ``need_restart = True`` and ``daemon_reload = True`` (if applicable)
        when the file is actually removed and *track* is True.
        """
        res = files.file(name=f"Remove {dest}", path=dest, present=False)
        return self._update_restart_signals(dest, res, track=track)

    def ensure_line(self, path, line, *, track=True, **kwargs):
        """Ensure a line is present or absent in a file.

        Sets ``need_restart = True`` when the file changes and *track* is True.
        """
        name = f"Ensure line in {path}"
        res = files.line(name=name, path=path, line=line, **kwargs)
        return self._update_restart_signals(path, res, track=track)

    def ensure_directory(self, path, *, owner="root", mode="755", track=True, **kwargs):
        """Ensure a directory exists on the remote host.

        Sets ``need_restart = True`` when the directory is created or modified
        and *track* is True.
        """
        name = kwargs.pop("name", f"Ensure directory {path}")
        res = files.directory(
            name=name, path=path, user=owner, group=owner, mode=mode, present=True, **kwargs
        )
        return self._update_restart_signals(path, res, track=track)

    def remove_directory(self, path, *, track=True, **kwargs):
        """Ensure a directory is removed from the remote host.

        Sets ``need_restart = True`` when the directory is actually removed
        and *track* is True.
        """
        name = kwargs.pop("name", f"Remove directory {path}")
        res = files.directory(name=name, path=path, present=False, **kwargs)
        return self._update_restart_signals(path, res, track=track)

    def _update_restart_signals(self, path, res, track=True):
        if res.changed and track:
            self.need_restart = True
            if str(path).startswith("/etc/systemd/system/"):
                self.daemon_reload = True
        return res
