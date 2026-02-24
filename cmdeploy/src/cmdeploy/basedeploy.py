import importlib.resources
import io
import os
from contextlib import contextmanager

from pyinfra import host
from pyinfra.facts.server import Command
from pyinfra.operations import files, server, systemd


def has_systemd():
    """Returns False during Docker image builds or any other non-systemd environment."""
    return os.path.isdir("/run/systemd/system")


def is_in_container() -> bool:
    """Return True if running inside a container (Docker, LXC, etc.)."""
    return (
        host.get_fact(
            Command,
            "systemd-detect-virt --container --quiet 2>/dev/null && echo yes || true",
        )
        == "yes"
    )


@contextmanager
def blocked_service_startup():
    """Prevent services from auto-starting during package installation.

    Installs a ``/usr/sbin/policy-rc.d`` that exits 101, blocking any
    service from being started by the package manager.  This avoids bind
    conflicts and CPU/RAM spikes during initial setup.  The file is removed
    when the context exits.
    """
    # For documentation about policy-rc.d, see:
    # https://people.debian.org/~hmh/invokerc.d-policyrc.d-specification.txt
    files.put(
        src=get_resource("policy-rc.d"),
        dest="/usr/sbin/policy-rc.d",
        user="root",
        group="root",
        mode="755",
    )
    yield
    files.file("/usr/sbin/policy-rc.d", present=False)


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


def activate_remote_units(units, daemon_reload) -> None:
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
    need_restart = False
    daemon_reload = False

    def install(self):
        pass

    def configure(self):
        pass

    def activate(self):
        pass

    def ensure_service(self, service, running=True, enabled=True):
        if running:
            verb = "Start and enable"
        else:
            verb = "Stop"
        systemd.service(
            name=f"{verb} {service}",
            service=service,
            running=running,
            enabled=enabled,
            restarted=self.need_restart if running else False,
            daemon_reload=self.daemon_reload,
        )
        self.need_restart = False
        self.daemon_reload = False

    def ensure_systemd_unit(self, src, **kwargs):
        dest_name = src.split("/")[-1].replace(".j2", "")
        dest = f"/etc/systemd/system/{dest_name}"
        if src.endswith(".j2"):
            return self.put_template(src, dest, **kwargs)
        return self.put_file(src, dest)

    def put_file(self, src, dest, executable=False):
        if isinstance(src, str):
            src = get_resource(src)
        mode = "755" if executable else "644"
        res = files.put(
            name=f"Upload {dest}", src=src, dest=dest, user="root", group="root", mode=mode
        )

        return self._update_restart_signals(dest, res)

    def put_template(self, src, dest, owner="root", **kwargs):
        if isinstance(src, str):
            src = get_resource(src)
        res = files.template(
            name=f"Upload {dest}",
            src=src,
            dest=dest,
            user=owner,
            group=owner,
            mode="644",
            **kwargs,
        )

        return self._update_restart_signals(dest, res)

    def remove_file(self, dest):
        res = files.file(name=f"Remove {dest}", path=dest, present=False)
        return self._update_restart_signals(dest, res)

    def ensure_line(self, path, line, **kwargs):
        name = kwargs.pop("name", f"Ensure line in {path}")
        res = files.line(name=name, path=path, line=line, **kwargs)
        return self._update_restart_signals(path, res)

    def ensure_directory(self, path, owner="root", mode="755", **kwargs):
        name = kwargs.pop("name", f"Ensure directory {path}")
        res = files.directory(
            name=name,
            path=path,
            user=owner,
            group=owner,
            mode=mode,
            present=True,
            **kwargs,
        )
        return self._update_restart_signals(path, res)

    def remove_directory(self, path, **kwargs):
        name = kwargs.pop("name", f"Remove directory {path}")
        res = files.directory(name=name, path=path, present=False, **kwargs)
        return self._update_restart_signals(path, res)

    def _update_restart_signals(self, path, res):
        if res.changed:
            self.need_restart = True
            if str(path).startswith("/etc/systemd/system/"):
                self.daemon_reload = True
        return res
