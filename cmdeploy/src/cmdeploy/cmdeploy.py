"""
Provides the `cmdeploy` entry point function,
along with command line option and subcommand parsing.
"""

import argparse
import importlib.resources
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
from pathlib import Path

import pyinfra
from chatmaild.config import read_config, write_initial_config
from packaging import version
from termcolor import colored

from . import dns, remote
from .sshexec import LocalExec, SSHExec

#
# cmdeploy sub commands and options
#


def init_cmd_options(parser):
    parser.add_argument(
        "chatmail_domain",
        action="store",
        help="fully qualified DNS domain name for your chatmail instance",
    )
    parser.add_argument(
        "--force",
        dest="recreate_ini",
        action="store_true",
        help="force reacreate ini file",
    )


def init_cmd(args, out):
    """Initialize chatmail config file."""
    mail_domain = args.chatmail_domain
    inipath = args.inipath
    if args.inipath.exists():
        if not args.recreate_ini:
            print(f"[WARNING] Path exists, not modifying: {inipath}")
            return 1
        else:
            print(
                f"[WARNING] Force argument was provided, deleting config file: {inipath}"
            )
            inipath.unlink()

    write_initial_config(inipath, mail_domain, overrides={})
    out.green(f"created config file for {mail_domain} in {inipath}")


def run_cmd_options(parser):
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="don't actually modify the server",
    )
    parser.add_argument(
        "--disable-mail",
        dest="disable_mail",
        action="store_true",
        help="install/upgrade the server, but disable postfix & dovecot for now",
    )
    parser.add_argument(
        "--website-only",
        action="store_true",
        help="only update/deploy the website, skipping full server upgrade/deployment, useful when you only changed/updated the web pages and don't need to re-run a full server upgrade",
    )
    parser.add_argument(
        "--skip-dns-check",
        dest="dns_check_disabled",
        action="store_true",
        help="disable checks nslookup for dns",
    )
    add_ssh_host_option(parser)


def run_cmd(args, out):
    """Deploy chatmail services on the remote server."""

    ssh_host = args.ssh_host if args.ssh_host else args.config.mail_domain
    sshexec = get_sshexec(ssh_host)
    require_iroh = args.config.enable_iroh_relay
    if not args.dns_check_disabled:
        remote_data = dns.get_initial_remote_data(sshexec, args.config.mail_domain)
        if not dns.check_initial_remote_data(remote_data, print=out.red):
            return 1

    env = os.environ.copy()
    env["CHATMAIL_INI"] = args.inipath
    env["CHATMAIL_WEBSITE_ONLY"] = "True" if args.website_only else ""
    env["CHATMAIL_DISABLE_MAIL"] = "True" if args.disable_mail else ""
    env["CHATMAIL_REQUIRE_IROH"] = "True" if require_iroh else ""
    deploy_path = importlib.resources.files(__package__).joinpath("run.py").resolve()
    pyinf = "pyinfra --dry" if args.dry_run else "pyinfra"

    cmd = f"{pyinf} --ssh-user root {ssh_host} {deploy_path} -y"
    if ssh_host in ["localhost", "@docker"]:
        cmd = f"{pyinf} @local {deploy_path} -y"

    if version.parse(pyinfra.__version__) < version.parse("3"):
        out.red("Please re-run scripts/initenv.sh to update pyinfra to version 3.")
        return 1

    try:
        retcode = out.check_call(cmd, env=env)
        if args.website_only:
            if retcode == 0:
                out.green("Website deployment completed.")
            else:
                out.red("Website deployment failed.")
        elif retcode == 0:
            out.green("Deploy completed, call `cmdeploy dns` next.")
        elif not remote_data["acme_account_url"]:
            out.red("Deploy completed but letsencrypt not configured")
            out.red("Run 'cmdeploy run' again")
            retcode = 0
        else:
            out.red("Deploy failed")
    except subprocess.CalledProcessError:
        out.red("Deploy failed")
        retcode = 1
    return retcode


def dns_cmd_options(parser):
    parser.add_argument(
        "--zonefile",
        dest="zonefile",
        type=pathlib.Path,
        default=None,
        help="write out a zonefile",
    )
    add_ssh_host_option(parser)


def dns_cmd(args, out):
    """Check DNS entries and optionally generate dns zone file."""
    ssh_host = args.ssh_host if args.ssh_host else args.config.mail_domain
    sshexec = get_sshexec(ssh_host, verbose=args.verbose)
    remote_data = dns.get_initial_remote_data(sshexec, args.config.mail_domain)
    if not remote_data:
        return 1

    if not remote_data["acme_account_url"]:
        out.red("could not get letsencrypt account url, please run 'cmdeploy run'")
        return 1

    if not remote_data["dkim_entry"]:
        out.red("could not determine dkim_entry, please run 'cmdeploy run'")
        return 1

    zonefile = dns.get_filled_zone_file(remote_data)

    if args.zonefile:
        args.zonefile.write_text(zonefile)
        out.green(f"DNS records successfully written to: {args.zonefile}")
        return 0

    retcode = dns.check_full_zone(
        sshexec, remote_data=remote_data, zonefile=zonefile, out=out
    )
    return retcode


def status_cmd_options(parser):
    add_ssh_host_option(parser)


def status_cmd(args, out):
    """Display status for online chatmail instance."""

    ssh_host = args.ssh_host if args.ssh_host else args.config.mail_domain
    sshexec = get_sshexec(ssh_host, verbose=args.verbose)

    out.green(f"chatmail domain: {args.config.mail_domain}")
    if args.config.privacy_mail:
        out.green("privacy settings: present")
    else:
        out.red("no privacy settings")

    for line in sshexec(remote.rshell.get_systemd_running):
        print(line)


def test_cmd_options(parser):
    parser.add_argument(
        "--slow",
        dest="slow",
        action="store_true",
        help="also run slow tests",
    )


def test_cmd(args, out):
    """Run local and online tests for chatmail deployment.

    This will automatically pip-install 'deltachat' if it's not available.
    """

    x = importlib.util.find_spec("deltachat")
    if x is None:
        out.check_call(f"{sys.executable} -m pip install deltachat")

    pytest_path = shutil.which("pytest")
    pytest_args = [
        pytest_path,
        "cmdeploy/src/",
        "-n4",
        "-rs",
        "-x",
        "-v",
        "--durations=5",
    ]
    if args.slow:
        pytest_args.append("--slow")
    ret = out.run_ret(pytest_args)
    return ret


def fmt_cmd_options(parser):
    parser.add_argument(
        "--check",
        "-c",
        action="store_true",
        help="only check but don't fix problems",
    )


def fmt_cmd(args, out):
    """Run formattting fixes on all chatmail source code."""

    chatmaild_dir = importlib.resources.files("chatmaild").resolve()
    cmdeploy_dir = chatmaild_dir.joinpath(
        "..", "..", "..", "cmdeploy", "src", "cmdeploy"
    ).resolve()
    sources = [str(chatmaild_dir), str(cmdeploy_dir)]

    format_args = [shutil.which("ruff"), "format"]
    check_args = [shutil.which("ruff"), "check"]

    if args.check:
        format_args.append("--diff")
    else:
        check_args.append("--fix")

    if not args.verbose:
        check_args.append("--quiet")
        format_args.append("--quiet")

    format_args.extend(sources)
    check_args.extend(sources)

    out.check_call(" ".join(format_args), quiet=not args.verbose)
    out.check_call(" ".join(check_args), quiet=not args.verbose)


def bench_cmd(args, out):
    """Run benchmarks against an online chatmail instance."""
    args = ["pytest", "--pyargs", "cmdeploy.tests.online.benchmark", "-vrx"]
    cmdstring = " ".join(args)
    out.green(f"[$ {cmdstring}]")
    subprocess.check_call(args)


def webdev_cmd(args, out):
    """Run local web development loop for static web pages."""
    from .www import main

    main()


#
# Parsing command line options and starting commands
#


class Out:
    """Convenience output printer providing coloring."""

    def red(self, msg, file=sys.stderr):
        print(colored(msg, "red"), file=file)

    def green(self, msg, file=sys.stderr):
        print(colored(msg, "green"), file=file)

    def __call__(self, msg, red=False, green=False, file=sys.stdout):
        color = "red" if red else ("green" if green else None)
        print(colored(msg, color), file=file)

    def check_call(self, arg, env=None, quiet=False):
        if not quiet:
            self(f"[$ {arg}]", file=sys.stderr)
        return subprocess.check_call(arg, shell=True, env=env)

    def run_ret(self, args, env=None, quiet=False):
        if not quiet:
            cmdstring = " ".join(args)
            self(f"[$ {cmdstring}]", file=sys.stderr)
        proc = subprocess.run(args, env=env, check=False)
        return proc.returncode


def add_ssh_host_option(parser):
    parser.add_argument(
        "--ssh-host",
        dest="ssh_host",
        help="Run commands on 'localhost', via '@docker', or on a specific SSH host "
        "instead of chatmail.ini's mail_domain.",
    )


def add_config_option(parser):
    parser.add_argument(
        "--config",
        dest="inipath",
        action="store",
        default=Path("chatmail.ini"),
        type=Path,
        help="path to the chatmail.ini file",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        dest="verbose",
        action="store_true",
        default=False,
        help="provide verbose logging",
    )


def add_subcommand(subparsers, func):
    name = func.__name__
    assert name.endswith("_cmd")
    name = name[:-4]
    doc = func.__doc__.strip()
    help = doc.split("\n")[0].strip(".")
    p = subparsers.add_parser(name, description=doc, help=help)
    p.set_defaults(func=func)
    add_config_option(p)
    return p


description = """
Setup your chatmail server configuration and
deploy it via SSH to your remote location.
"""


def get_parser():
    """Return an ArgumentParser for the 'cmdeploy' CLI"""

    parser = argparse.ArgumentParser(description=description.strip())
    subparsers = parser.add_subparsers(title="subcommands")

    # find all subcommands in the module namespace
    glob = globals()
    for name, func in glob.items():
        if name.endswith("_cmd"):
            subparser = add_subcommand(subparsers, func)
            addopts = glob.get(name + "_options")
            if addopts is not None:
                addopts(subparser)

    return parser


def get_sshexec(ssh_host: str, verbose=True):
    if ssh_host in ["localhost", "@local"]:
        return LocalExec(verbose, docker=False)
    elif ssh_host == "@docker":
        return LocalExec(verbose, docker=True)
    if verbose:
        print(f"[ssh] login to {ssh_host}")
    return SSHExec(ssh_host, verbose=verbose)


def main(args=None):
    """Provide main entry point for 'cmdeploy' CLI invocation."""
    parser = get_parser()
    args = parser.parse_args(args=args)
    if not hasattr(args, "func"):
        return parser.parse_args(["-h"])

    out = Out()
    kwargs = {}
    if args.func.__name__ not in ("init_cmd", "fmt_cmd"):
        if not args.inipath.exists():
            out.red(f"expecting {args.inipath} to exist, run init first?")
            raise SystemExit(1)
        try:
            args.config = read_config(args.inipath)
        except Exception as ex:
            out.red(ex)
            raise SystemExit(1)

    try:
        res = args.func(args, out, **kwargs)
        if res is None:
            res = 0
        return res
    except KeyboardInterrupt:
        out.red("KeyboardInterrupt")
        sys.exit(130)


if __name__ == "__main__":
    main()
