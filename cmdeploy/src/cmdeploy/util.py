"""Shared utility functions for cmdeploy."""

import subprocess
import textwrap
from pathlib import Path


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


def get_git_hash():
    """Return the local HEAD commit hash, or None."""
    result = shell(
        "git rev-parse HEAD",
        cwd=str(_project_root()),
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def get_version_string():
    """Return ``git_hash\\ngit_diff`` for the local working tree.

    Used by :class:`~cmdeploy.deployers.GithashDeployer` to write
    ``/etc/chatmail-version`` and by ``lxc-status`` to compare
    the deployed state against the local checkout.
    """
    git_hash = get_git_hash() or "unknown"
    try:
        git_diff = shell("git diff", cwd=str(_project_root())).stdout
    except Exception:
        git_diff = ""
    return git_hash + "\n" + git_diff
