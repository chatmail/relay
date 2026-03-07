"""Shared utility functions for cmdeploy."""

import fcntl
import subprocess
import sys
import textwrap
from pathlib import Path


def _project_root():
    """Return the project root directory."""
    return Path(__file__).resolve().parent.parent.parent.parent


def collapse(text):
    """Dedent, join lines, and strip a (triple-quoted) string.

    Handy for writing shell commands across multiple lines::

        cmd = collapse(f\"\"\"
            cmdeploy run
            --config {ct.ini}
            --ssh-host {ct.domain}
        \"\"\")
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


def _chatmaild_default_dist_dir():
    return _project_root() / "chatmaild" / "dist"


def build_chatmaild_sdist(dist_dir=None):
    """Build the chatmaild sdist if not already present (idempotent, process-safe)."""

    if dist_dir is None:
        dist_dir = _chatmaild_default_dist_dir()
    dist_dir = Path(dist_dir).resolve()
    dist_dir.mkdir(parents=True, exist_ok=True)

    lockfile = dist_dir.parent / ".dist.lock"
    with open(lockfile, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        existing = [p for p in dist_dir.iterdir() if p.suffix == ".gz"]
        if existing:
            return existing[0]
        subprocess.check_output(
            [sys.executable, "-m", "build", "-n"]
            + ["--sdist", "chatmaild", "--outdir", str(dist_dir)],
            cwd=str(_project_root()),
        )
        return get_chatmaild_sdist(dist_dir)


def get_chatmaild_sdist(dist_dir=None):
    """Return the path to the pre-built chatmaild sdist."""
    if dist_dir is None:
        dist_dir = _chatmaild_default_dist_dir()

    entries = list(Path(dist_dir).iterdir())
    if len(entries) == 0:
        raise FileNotFoundError(f"dist directory is empty: {dist_dir}")
    if len(entries) > 1:
        raise ValueError(f"expected one file in {dist_dir}, found {len(entries)}")
    return entries[0]
