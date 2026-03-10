"""
Provides the `cmdeploy` entry point function,
along with command line option and subcommand parsing.
"""

import argparse
import importlib.resources
import os
import pathlib
import shutil
import subprocess
import sys
from pathlib import Path

import pyinfra
from chatmaild.config import read_config, write_initial_config
from packaging import version

from . import dns, remote
from .lxc.cli import (
    lxc_start_cmd,
    lxc_start_cmd_options,
    lxc_status_cmd,
    lxc_status_cmd_options,
    lxc_stop_cmd,
    lxc_stop_cmd_options,
    lxc_test_cmd,
    lxc_test_cmd_options,
)
from .lxc.incus import DNSConfigurationError
from .sshexec import (
    LocalExec,
    SSHExec,
    resolve_host_from_ssh_config,
    resolve_key_from_ssh_config,
)
from .util import Out
from .www import main as webdev_main

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
    add_ssh_config_option(parser)


def run_cmd(args, out):
    """Deploy chatmail services on the remote server."""

    ssh_host = args.ssh_host if args.ssh_host else args.config.mail_domain
    sshexec = get_sshexec(ssh_host, ssh_config=args.ssh_config)
    require_iroh = args.config.enable_iroh_relay
    strict_tls = args.config.tls_cert_mode == "acme"
    if not args.dns_check_disabled:
        remote_data = dns.get_initial_remote_data(sshexec, args.config.mail_domain)
        if not dns.check_initial_remote_data(
            remote_data, strict_tls=strict_tls, print=out.red
        ):
            return 1

    env = os.environ.copy()
    env["CHATMAIL_INI"] = args.inipath
    env["CHATMAIL_WEBSITE_ONLY"] = "True" if args.website_only else ""
    env["CHATMAIL_DISABLE_MAIL"] = "True" if args.disable_mail else ""
    env["CHATMAIL_REQUIRE_IROH"] = "True" if require_iroh else ""
    if not args.dns_check_disabled:
        env["CHATMAIL_ADDR_V4"] = remote_data.get("A") or ""
        env["CHATMAIL_ADDR_V6"] = remote_data.get("AAAA") or ""
    env["DEBIAN_FRONTEND"] = "noninteractive"
    env["TERM"] = "linux"
    deploy_path = importlib.resources.files(__package__).joinpath("run.py").resolve()
    pyinf = "pyinfra --dry" if args.dry_run else "pyinfra"

    cmd = f"{pyinf} --ssh-user root {ssh_host} {deploy_path} -y"
    ssh_config = args.ssh_config
    if ssh_config:
        ssh_config = str(Path(ssh_config).resolve())

        # Use pyinfra's native SSH data keys to configure the connection directly
        # rather than relying on paramiko config parsing (see also sshexec.py)
        ip = resolve_host_from_ssh_config(ssh_host, ssh_config)
        key = resolve_key_from_ssh_config(ssh_host, ssh_config)
        data_args = f"--data ssh_hostname={ip} --data ssh_known_hosts_file=/dev/null"
        if key:
            data_args += f" --data ssh_key={key}"
        cmd = f"{pyinf} --ssh-user root {ssh_host} {deploy_path} -y {data_args}"
    if ssh_host in ["localhost", "@docker"]:
        if ssh_host == "@docker":
            env["CHATMAIL_NOPORTCHECK"] = "True"
            env["CHATMAIL_NOSYSCTL"] = "True"
        cmd = f"{pyinf} @local {deploy_path} -y"

    if version.parse(pyinfra.__version__) < version.parse("3"):
        out.red("Please re-run scripts/initenv.sh to update pyinfra to version 3.")
        return 1

    try:
        ret = out.shell(cmd, env=env)
        if ret:
            out.red("Deploy failed")
            return 1
        if args.website_only:
            out.green("Website deployment completed.")
        elif (
            not args.dns_check_disabled
            and strict_tls
            and not remote_data["acme_account_url"]
        ):
            out.red("Deploy completed but letsencrypt not configured")
            out.red("Run 'cmdeploy run' again")
        else:
            out.green("Deploy completed, call `cmdeploy dns` next.")
        return 0
    except subprocess.CalledProcessError:
        out.red("Deploy failed")
        return 1


def dns_cmd_options(parser):
    parser.add_argument(
        "--zonefile",
        dest="zonefile",
        type=pathlib.Path,
        default=None,
        help="write DNS records in standard BIND format to the given file",
    )
    add_ssh_host_option(parser)
    add_ssh_config_option(parser)


def dns_cmd(args, out):
    """Check DNS entries and optionally generate dns zone file."""
    ssh_host = args.ssh_host if args.ssh_host else args.config.mail_domain
    sshexec = get_sshexec(ssh_host, verbose=args.verbose, ssh_config=args.ssh_config)
    tls_cert_mode = args.config.tls_cert_mode
    strict_tls = tls_cert_mode == "acme"
    remote_data = dns.get_initial_remote_data(sshexec, args.config.mail_domain)
    if not dns.check_initial_remote_data(remote_data, strict_tls=strict_tls):
        return 1

    if strict_tls and not remote_data["acme_account_url"]:
        out.red("could not get letsencrypt account url, please run 'cmdeploy run'")
        return 1

    if not remote_data["dkim_entry"]:
        out.red("could not determine dkim_entry, please run 'cmdeploy run'")
        return 1

    remote_data["strict_tls"] = strict_tls
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
    add_ssh_config_option(parser)


def status_cmd(args, out):
    """Display status for online chatmail instance."""

    ssh_host = args.ssh_host if args.ssh_host else args.config.mail_domain
    sshexec = get_sshexec(ssh_host, verbose=args.verbose, ssh_config=args.ssh_config)

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
    add_ssh_host_option(parser)
    add_ssh_config_option(parser)


def test_cmd(args, out):
    """Run local and online tests for chatmail deployment."""

    env = os.environ.copy()
    env["CHATMAIL_INI"] = str(args.inipath.resolve())

    pytest_path = shutil.which("pytest")
    pytest_args = [
        pytest_path,
        "cmdeploy/src/",
        "-rs",
        "-x",
        "-vv" if args.verbose > 1 else "-v",
        "-s",
        "--durations=5",
    ]
    if args.slow:
        pytest_args.append("--slow")
    if args.ssh_host:
        pytest_args.extend(["--ssh-host", args.ssh_host])
    if args.ssh_config:
        pytest_args.extend(["--ssh-config", str(Path(args.ssh_config).resolve())])
    ret = out.shell(" ".join(pytest_args), env=env)
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

    out.shell(" ".join(format_args), quiet=not args.verbose)
    out.shell(" ".join(check_args), quiet=not args.verbose)


def bench_cmd(args, out):
    """Run benchmarks against an online chatmail instance."""
    args = ["pytest", "--pyargs", "cmdeploy.tests.online.benchmark", "-vrx"]
    cmdstring = " ".join(args)
    out.green(f"[$ {cmdstring}]")
    subprocess.check_call(args)


def webdev_cmd(args, out):
    """Run local web development loop for static web pages."""
    webdev_main()


#
# Parsing command line options and starting commands
#


def add_ssh_host_option(parser):
    parser.add_argument(
        "--ssh-host",
        dest="ssh_host",
        help="Run commands on 'localhost', via '@docker', or on a specific SSH host "
        "instead of chatmail.ini's mail_domain.",
    )


def add_ssh_config_option(parser):
    parser.add_argument(
        "--ssh-config",
        dest="ssh_config",
        type=Path,
        default=None,
        help="Path to an SSH config file (e.g. lxconfigs/ssh-config).",
    )


def add_config_option(parser):
    parser.add_argument(
        "--config",
        dest="inipath",
        action="store",
        default=Path(os.environ.get("CHATMAIL_INI", "chatmail.ini")),
        type=Path,
        help="path to the chatmail.ini file",
    )


def add_subcommand(subparsers, func, add_config=True):
    name = func.__name__
    assert name.endswith("_cmd")
    name = name[:-4].replace("_", "-")
    doc = func.__doc__.strip()
    help = doc.split("\n")[0].strip(".")
    p = subparsers.add_parser(name, description=doc, help=help)
    p.set_defaults(func=func)
    if add_config:
        add_config_option(p)
    p.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        action="count",
        default=0,
        help="increase verbosity (can be repeated: -v, -vv)",
    )
    return p


description = """
Setup your chatmail server configuration and
deploy it via SSH to your remote location.
"""

# Explicit subcommand registry: (cmd_func, options_func_or_None, needs_config).
# LXC commands don't need a chatmail.ini (no config); all others do.
SUBCOMMANDS = [
    (init_cmd, init_cmd_options, True),
    (run_cmd, run_cmd_options, True),
    (dns_cmd, dns_cmd_options, True),
    (status_cmd, status_cmd_options, True),
    (test_cmd, test_cmd_options, True),
    (fmt_cmd, fmt_cmd_options, True),
    (bench_cmd, None, True),
    (webdev_cmd, None, True),
    (lxc_start_cmd, lxc_start_cmd_options, False),
    (lxc_stop_cmd, lxc_stop_cmd_options, False),
    (lxc_status_cmd, lxc_status_cmd_options, False),
    (lxc_test_cmd, lxc_test_cmd_options, False),
]


def get_parser():
    """Return an ArgumentParser for the 'cmdeploy' CLI"""

    parser = argparse.ArgumentParser(description=description.strip())
    parser.set_defaults(func=None, inipath=None)
    subparsers = parser.add_subparsers(title="subcommands")

    for func, addopts, needs_config in SUBCOMMANDS:
        subparser = add_subcommand(subparsers, func, add_config=needs_config)
        if addopts is not None:
            addopts(subparser)

    return parser


def get_sshexec(ssh_host: str, verbose=True, ssh_config=None):
    if ssh_host in ["localhost", "@local"]:
        return LocalExec(verbose, docker=False)
    elif ssh_host == "@docker":
        return LocalExec(verbose, docker=True)
    if verbose:
        print(f"[ssh] login to {ssh_host}")
    return SSHExec(ssh_host, verbose=verbose, ssh_config=ssh_config)


def main(args=None):
    """Provide main entry point for 'cmdeploy' CLI invocation."""
    parser = get_parser()
    args = parser.parse_args(args=args)
    if args.func is None:
        return parser.parse_args(["-h"])

    out = Out(verbosity=args.verbose)
    kwargs = {}

    if args.inipath is not None and args.func.__name__ not in ("init_cmd", "fmt_cmd"):
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
    except DNSConfigurationError as exc:
        out.red(str(exc))
        return 1
    except KeyboardInterrupt:
        out.red("KeyboardInterrupt")
        sys.exit(130)


if __name__ == "__main__":
    main()
