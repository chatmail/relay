import inspect
import os
import sys
from queue import Queue

import execnet

from . import remote


class FuncError(Exception):
    pass


def bootstrap_remote(gateway, remote=remote):
    """Return a command channel which can execute remote functions."""
    source_init_path = inspect.getfile(remote)
    basedir = os.path.dirname(source_init_path)
    name = os.path.basename(basedir)

    # rsync sourcedir to remote host
    remote_pkg_path = f"/root/from-cmdeploy/{name}"
    q = Queue()
    finish = lambda: q.put(None)
    rsync = execnet.RSync(sourcedir=basedir, verbose=False)
    rsync.add_target(gateway, remote_pkg_path, finishedcallback=finish, delete=True)
    rsync.send()
    q.get()

    # start sshexec bootstrap and return its command channel
    remote_sys_path = os.path.dirname(remote_pkg_path)
    channel = gateway.remote_exec(
        f"""
        import sys
        sys.path.insert(0, {remote_sys_path!r})
        from remote._sshexec_bootstrap import main
        main(channel)
    """
    )
    return channel


def print_stderr(item="", end="\n"):
    print(item, file=sys.stderr, end=end)
    sys.stderr.flush()


class SSHExec:
    RemoteError = execnet.RemoteError
    FuncError = FuncError

    def __init__(
        self, host, verbose=False, python="python3", timeout=60, ssh_config=None
    ):
        spec = f"ssh=root@{host}//python={python}"
        if ssh_config:
            spec += f"//ssh_config={ssh_config}"
        self.gateway = execnet.makegateway(spec)
        self._remote_cmdloop_channel = bootstrap_remote(self.gateway, remote)
        self.timeout = timeout
        self.verbose = verbose

    def __call__(self, call, kwargs=None, log_callback=None):
        if kwargs is None:
            kwargs = {}
        assert call.__module__.startswith("cmdeploy.remote")
        modname = call.__module__.replace("cmdeploy.", "")
        self._remote_cmdloop_channel.send((modname, call.__name__, kwargs))
        while 1:
            code, data = self._remote_cmdloop_channel.receive(timeout=self.timeout)
            if log_callback is not None and code == "log":
                log_callback(data)
            elif code == "finish":
                return data
            elif code == "error":
                raise self.FuncError(data)

    def logged(self, call, kwargs):
        title = call.__doc__
        if not title:
            title = call.__name__
        if self.verbose:
            print_stderr("[ssh] " + title)
            return self(call, kwargs, log_callback=print_stderr)
        else:
            print_stderr(title, end="")
            res = self(call, kwargs, log_callback=remote.rshell.log_progress)
            print_stderr()
            return res


class LocalExec:
    FuncError = FuncError

    def __init__(self, verbose=False, docker=False):
        self.verbose = verbose
        self.docker = docker

    def __call__(self, call, kwargs=None, log_callback=None):
        if kwargs is None:
            kwargs = {}
        return call(**kwargs)

    def logged(self, call, kwargs: dict):
        title = call.__doc__
        if not title:
            title = call.__name__
        where = "locally"
        if self.docker:
            if call == remote.rdns.perform_initial_checks:
                kwargs["pre_command"] = "docker exec chatmail "
                where = "in docker"
        if self.verbose:
            print_stderr(f"Running {where}: {title}(**{kwargs})")
            return self(call, kwargs, log_callback=print_stderr)
        else:
            print_stderr(title, end="")
            res = self(call, kwargs, log_callback=remote.rshell.log_progress)
            print_stderr()
            return res


# pyinfra exposes a ``ssh_config_file`` data key that *should* let
# paramiko parse an SSH config file directly.  In practice it silently
# fails to connect (zero hosts / zero operations), so we resolve the
# hostname and identity-file ourselves and pass them via
# ``--data ssh_hostname`` / ``--data ssh_key`` instead.
# Execnet uses ssh natively (and not paramiko) and doesn't have this problem.


def _get_from_ssh_config(host, ssh_config_path, key):
    """Internal helper to parse a value for a specific key from ssh-config."""
    current_hosts = []
    found_value = None
    with open(ssh_config_path) as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if not parts:
                continue
            directive = parts[0].lower()
            if directive == "host":
                if host in current_hosts and found_value:
                    return found_value
                current_hosts = parts[1].split()
                found_value = None
            elif directive == key.lower():
                found_value = parts[1]
    if host in current_hosts and found_value:
        return found_value
    return None


def resolve_host_from_ssh_config(host, ssh_config_path):
    """Resolve a host alias to its IP from an ssh-config file."""
    return _get_from_ssh_config(host, ssh_config_path, "Hostname") or host


def resolve_key_from_ssh_config(host, ssh_config_path):
    """Resolve a host alias to its IdentityFile from an ssh-config file."""
    return _get_from_ssh_config(host, ssh_config_path, "IdentityFile")
