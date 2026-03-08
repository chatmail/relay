"""Shared utility functions for cmdeploy."""

import os
import shutil
import subprocess
import sys
import textwrap
import time
from contextlib import contextmanager
from pathlib import Path

from termcolor import colored


class Out:
    """Convenience output printer providing coloring and section formatting."""

    def __init__(self, sepchar="\u2501", prefix="", verbosity=0):
        self.section_timings = []
        self.prefix = prefix
        self.sepchar = sepchar
        self.verbosity = verbosity
        env_width = os.environ.get("_CMDEPLOY_WIDTH")
        if env_width:
            self.section_width = int(env_width)
        else:
            self.section_width = shutil.get_terminal_size((80, 24)).columns

    def new_prefixed_out(self, newprefix="  "):
        """Return a new Out with an extended prefix,
        sharing section_timings with the parent.
        """
        out = Out(
            sepchar=self.sepchar,
            prefix=self.prefix + newprefix,
            verbosity=self.verbosity,
        )
        out.section_timings = self.section_timings
        return out

    def red(self, msg, file=sys.stderr):
        print(colored(self.prefix + msg, "red"), file=file, flush=True)

    def green(self, msg, file=sys.stderr):
        print(colored(self.prefix + msg, "green"), file=file, flush=True)

    def print(self, msg="", **kwargs):
        """Print to stdout with automatic flush."""
        if msg:
            msg = self.prefix + msg
        print(msg, flush=True, **kwargs)

    def _format_header(self, title):
        """Return a formatted section header string."""
        width = self.section_width - len(self.prefix)
        bar = self.sepchar * (width - len(title) - 5)
        return f"{self.sepchar * 3} {title} {bar}"

    @contextmanager
    def section(self, title):
        """Context manager that prints a section header and records elapsed time."""
        self.green(self._format_header(title))
        t0 = time.time()
        yield
        elapsed = time.time() - t0
        self.section_timings.append((title, elapsed))

    def section_line(self, title):
        """Print a section header without timing."""
        self.green(self._format_header(title))

    def shell(self, cmd, quiet=False, **kwargs):
        """Print *cmd*, run it, and re-print its output with the current prefix.

        *cmd* is passed through :func:`collapse`, so callers
        can use triple-quoted f-strings freely.
        Stdout and stderr are merged, read line-by-line,
        and each line is printed with ``self.prefix`` prepended.
        When the command exits non-zero, a red error line is printed.
        """
        cmd = collapse(cmd)
        if not quiet:
            self.print(f"$ {cmd}")
        indent = self.prefix + "  "
        env = kwargs.pop("env", None)
        if env is None:
            env = os.environ.copy()
        env["_CMDEPLOY_WIDTH"] = str(self.section_width - len(indent))
        proc = subprocess.Popen(
            cmd,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            **kwargs,
        )
        for line in proc.stdout:
            sys.stdout.write(indent + line)
            sys.stdout.flush()
        ret = proc.wait()
        if ret:
            self.red(f"command failed with exit code {ret}: {cmd}")
        return ret


def _project_root():
    """Return the project root directory."""
    return Path(__file__).resolve().parent.parent.parent.parent


def collapse(text):
    """Dedent, join lines, and strip a (triple-quoted) string.

    Handy for writing shell commands across multiple lines::

        cmd = collapse(f\"""
            cmdeploy run
            --config {ct.ini}
            --ssh-host {ct.domain}
        \""")
    """
    return textwrap.dedent(text).replace("\n", " ").strip()


def shell(cmd, check=False, **kwargs):
    """Run a shell command string with sensible defaults.

    *cmd* is passed through :func:`collapse` first, so callers
    can use triple-quoted f-strings freely.
    Captures stdout/stderr by default; pass ``capture_output=False``
    to stream output to the terminal instead.
    """
    if "capture_output" not in kwargs and "stdout" not in kwargs:
        kwargs["capture_output"] = True
    return subprocess.run(collapse(cmd), shell=True, text=True, check=check, **kwargs)


def get_git_hash(root=None):
    """Return the local HEAD commit hash, or None."""
    if root is None:
        root = _project_root()
    result = shell(
        "git rev-parse HEAD",
        cwd=str(root),
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def get_version_string(root=None):
    """Return ``git_hash\\ngit_diff`` for the local working tree.

    Used by :class:`~cmdeploy.deployers.GithashDeployer` to write
    ``/etc/chatmail-version`` and by ``lxc-status`` to compare
    the deployed state against the local checkout.
    """
    if root is None:
        root = _project_root()
    git_hash = get_git_hash(root=root) or "unknown"
    try:
        git_diff = shell("git diff", cwd=str(root)).stdout.strip()
    except Exception:
        git_diff = ""
    if git_diff:
        return f"{git_hash}\n{git_diff}"
    return git_hash
