"""lxc-start/stop/status/test subcommands for testing with local containers."""

import os
import time

from ..util import get_git_hash, get_version_string, shell
from .incus import Incus, RelayContainer

RELAY_NAMES = ("test0", "test1")


# -------------------------------------------------------------------
# lxc-start
# -------------------------------------------------------------------


def lxc_start_cmd_options(parser):
    _add_name_args(
        parser,
        help_text="User relay name(s) to create (default: test0).",
    )
    parser.add_argument(
        "--ipv4-only",
        dest="ipv4_only",
        action="store_true",
        help="Create an IPv4-only container.",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run 'cmdeploy run' on each container after starting it.",
    )


def lxc_start_cmd(args, out):
    """Create/Ensure and start LXC relay and DNS containers."""

    with out.section("Preparing container setup"):
        _lxc_start_cmd(args, out)


def _lxc_start_cmd(args, out):
    ix = Incus(out)
    sub = out.new_prefixed_out()
    out.green("Ensuring base image ...")
    ix.ensure_base_image()
    out.green("Ensuring DNS container (ns-localchat) ...")
    dns_ct = ix.get_dns_container()
    dns_ct.ensure()
    sub.print(f"DNS container IP: {dns_ct.ipv4}")

    names = args.names if args.names else RELAY_NAMES
    relays = list(ix.get_container(n) for n in names)
    for ct in relays:
        out.green(f"Ensuring container {ct.name!r} ({ct.domain}) ...")
        ct.ensure()
        ip = ct.ipv4

        sub.print("Configuring container hostname ...")
        ct.configure_hosts(ip)

        sub.print(f"Writing {ct.ini.name} ...")
        ct.write_ini(disable_ipv6=args.ipv4_only)
        sub.print(f"Config: {ct.ini}")
        if args.ipv4_only:
            ct.disable_ipv6()
            ipv6 = None
        else:
            output = ct.bash(
                "ip -6 addr show scope global -deprecated"
                " | grep -oP '(?<=inet6 )[^/]+'",
                check=False,
            )
            ipv6 = output.strip() if output else None
        sub.print(f"{_format_addrs(ip, ipv6)}")

        sub.green(f"Container {ct.name!r} ready: {ct.domain} -> {ip}")
        out.print()

    # Reset DNS zones only for the containers we just started
    started_cnames = {ct.name for ct in relays}
    managed = ix.list_managed()
    started = [c for c in managed if c["name"] in started_cnames]

    if started:
        out.print(
            f"Resetting DNS zones for {len(started)} domain(s) (A + AAAA records) ..."
        )
        dns_ct.reset_dns_records(dns_ct.ipv4, started)

        for ct in relays:
            if ct.name in started_cnames:
                sub.print(f"Configuring DNS in {ct.name} ...")
                ct.configure_dns(dns_ct.ipv4)

    # Generate the unified SSH config
    out.green("Writing ssh-config ...")
    ssh_cfg = ix.write_ssh_config()
    sub.print(f"{ssh_cfg}")

    # Verify SSH via the generated config
    for ct in relays:
        sub.print(f"Verifying SSH to {ct.name} via ssh-config ...")
        if ct.verify_ssh(ssh_cfg):
            sub.print(f"SSH OK: ssh -F lxconfigs/ssh-config {ct.domain}")
        else:
            sub.red(f"WARNING: SSH verification failed for {ct.name}")

    # Print integration suggestions
    ssh_cfg = ix.ssh_config_path
    if not ix.check_ssh_include():
        sub.green(
            "\n(Optional) To use containers from any SSH client, add to ~/.ssh/config:"
        )
        sub.green(f"    Include {ssh_cfg}")

    # Optionally run cmdeploy run on each relay
    if args.run:
        for ct in relays:
            with out.section(f"cmdeploy run: {ct.sname} ({ct.domain})"):
                ret = _run_cmdeploy("run", ct, ix, out, extra=["--skip-dns-check"])
                if ret:
                    out.red(f"Deploy to {ct.sname} failed (exit {ret})")
                    return ret


# -------------------------------------------------------------------
# lxc-stop
# -------------------------------------------------------------------


def lxc_stop_cmd_options(parser):
    parser.add_argument(
        "--destroy",
        action="store_true",
        help="Delete containers and their config files after stopping.",
    )
    parser.add_argument(
        "--destroy-all",
        dest="destroy_all",
        action="store_true",
        help="Like --destroy, but also remove the ns-localchat DNS container.",
    )
    _add_name_args(
        parser,
        help_text="Container name(s) to stop (default: test0 + test1).",
    )


def lxc_stop_cmd(args, out):
    """Stop (and optionally destroy) local LXC relay containers."""
    ix = Incus(out)
    names = args.names or RELAY_NAMES
    destroy = args.destroy or args.destroy_all

    for ct in map(ix.get_container, names):
        if destroy:
            out.green(f"Destroying container {ct.name!r} ...")
            ct.destroy()
        else:
            out.green(f"Stopping container {ct.name!r} ...")
            ct.stop(force=True)

    if args.destroy_all:
        dns_ct = ix.get_dns_container()
        out.green(f"Destroying DNS container {dns_ct.name!r} ...")
        dns_ct.destroy()
        ix.delete_images()

    if destroy:
        ix.write_ssh_config()
        out.green("LXC containers destroyed.")
    else:
        out.green("LXC containers stopped.")


# -------------------------------------------------------------------
# lxc-test
# -------------------------------------------------------------------


def lxc_test_cmd_options(parser):
    parser.add_argument(
        "--one",
        action="store_true",
        help="Only deploy and test against test0 (skip test1).",
    )


def lxc_test_cmd(args, out):
    """Run full LXC pipeline: start, deploy, DNS, zone files, and tests.

    All commands run directly on the host using
    ``--ssh-config lxconfigs/ssh-config`` for SSH access.
    """
    ix = Incus(out)
    t_total = time.time()
    relay_names = list(RELAY_NAMES)
    if args.one:
        relay_names = relay_names[:1]

    local_hash = get_git_hash()

    # Per-relay: start, deploy, then snapshot the first relay as a
    # reusable image so the second relay launches pre-deployed.
    ipv4_only_flags = {RELAY_NAMES[0]: False, RELAY_NAMES[1]: True}

    for ct in map(ix.get_container, relay_names):
        name = ct.sname
        ipv4_only = ipv4_only_flags.get(name, False)
        v_flag = " -" + "v" * out.verbosity if out.verbosity > 0 else ""
        start_cmd = f"cmdeploy{v_flag} lxc-start {name}"
        if ipv4_only:
            start_cmd += " --ipv4-only"
        with out.section(f"cmdeploy lxc-start: {name}"):
            ret = out.shell(start_cmd, cwd=str(ix.project_root))
            if ret:
                return ret

        status = _deploy_status(ct, local_hash, ix)
        with out.section(f"cmdeploy run: {name}"):
            if "IN-SYNC" in status:
                out.print(f"{name} is {status}, skipping")
            else:
                ret = _run_cmdeploy("run", ct, ix, out, extra=["--skip-dns-check"])
                if ret:
                    out.red(f"Deploy to {name} failed (exit {ret})")
                    return ret

        # Snapshot the first relay so subsequent ones launch pre-deployed
        if not ix.find_relay_image():
            with out.section("lxc-test: caching relay image"):
                ct.publish_as_relay_image()

    for ct in map(ix.get_container, relay_names):
        with out.section(f"cmdeploy dns: {ct.sname} ({ct.domain})"):
            ret = _run_cmdeploy("dns", ct, ix, out, extra=["--zonefile", str(ct.zone)])
            if ret:
                out.red(f"DNS for {ct.sname} failed (exit {ret})")
                return ret

    with out.section(f"lxc-test: loading DNS zones {' & '.join(relay_names)}"):
        dns_ct = ix.get_dns_container()
        for ct in map(ix.get_container, relay_names):
            if ct.zone.exists():
                zone_data = ct.zone.read_text()
                out.print(f"Loading {ct.zone} into PowerDNS ...")
                dns_ct.set_dns_records(zone_data)

    with out.section("cmdeploy test"):
        first = ix.get_container(relay_names[0])
        env = None
        if len(relay_names) > 1:
            env = os.environ.copy()
            env["CHATMAIL_DOMAIN2"] = ix.get_container(relay_names[1]).domain
        ret = _run_cmdeploy("test", first, ix, out, **({"env": env} if env else {}))
        if ret:
            out.red(f"Tests failed (exit {ret})")
            return ret

    elapsed = time.time() - t_total
    out.section_line(f"lxc-test complete ({elapsed:.1f}s)")
    if out.section_timings:
        out.print("Section timings:")
        for name, secs in out.section_timings:
            out.print(f"  {name:.<50s} {secs:5.1f}s")
        out.print(f"  {'total':.<50s} {elapsed:5.1f}s")
    out.section_timings.clear()
    return 0


# -------------------------------------------------------------------
# lxc-status
# -------------------------------------------------------------------


def lxc_status_cmd_options(parser):
    pass


def lxc_status_cmd(args, out):
    """Show status of local LXC chatmail containers."""
    ix = Incus(out)
    containers = ix.list_managed()
    if not containers:
        out.red("No LXC containers found.  Run 'cmdeploy lxc-start' first.")
        return 1

    local_hash = get_git_hash()

    # Get storage pool path for display
    storage_path = None
    data = ix.run_json(["storage", "show", "default"], check=False)
    if data:
        storage_path = data.get("config", {}).get("source")
    msg = "Container status"
    if storage_path:
        msg += f": {storage_path}"
    out.section_line(msg)

    dns_ip = None
    for c in containers:
        _print_container_status(out, c, ix, local_hash)
        if c["name"] == ix.get_dns_container().name:
            dns_ip = c["ip"]

    out.section_line("Host ssh and DNS configuration")
    _print_ssh_status(out, ix)
    _print_dns_forwarding_status(out, dns_ip)
    return 0


def _print_container_status(out, c, ix, local_hash):
    """Print name/status, domain/IPs, and RAM for one container."""
    cname = c["name"]
    is_running = c.get("status") == "Running"
    ct = ix.get_container(cname)

    # First line: name + running/STOPPED + deploy status
    if not is_running:
        tag = "STOPPED"
    elif not isinstance(ct, RelayContainer):
        tag = "running"
    else:
        tag = f"running {_deploy_status(ct, local_hash, ix)}"
    out.print(f"{cname:20s} {tag}")

    # Second line: domain, IPv4, IPv6
    domain = c.get("domain", "")
    ip = c.get("ip") or "?"
    ipv6 = c.get("ipv6")
    out.print(f"{domain:20s} {_format_addrs(ip, ipv6)}")

    # Third line: RAM (RSS), config
    detail_out = out.new_prefixed_out(" " * 21)
    try:
        used, total = ct.rss_mib()
    except Exception:
        ram_str = "RSS ?"
    else:
        ram_str = f"RSS {used}/{total} MiB ({used * 100 // total}%)"

    if isinstance(ct, RelayContainer):
        detail = f"{ram_str}, config: {os.path.relpath(ct.ini)}"
    else:
        detail = ram_str

    detail_out.print(detail)
    out.print()


def _print_ssh_status(out, ix):
    """Print SSH integration status."""
    ssh_cfg = ix.ssh_config_path
    if ix.check_ssh_include():
        out.green("SSH: ~/.ssh/config includes lxconfigs/ssh-config ✓")
    else:
        out.red("SSH: ~/.ssh/config does NOT include lxconfigs/ssh-config")
        sub = out.new_prefixed_out()
        sub.print("Add to ~/.ssh/config:")
        sub.print(f"    Include {ssh_cfg}")


def _print_dns_forwarding_status(out, dns_ip):
    """Print host DNS forwarding status for .localchat."""
    sub = out.new_prefixed_out()
    if not dns_ip:
        out.red("DNS: ns-localchat container not found")
        return
    try:
        rv = shell("resolvectl status incusbr0")
        dns_ok = dns_ip in rv.stdout and "localchat" in rv.stdout
    except Exception:
        dns_ok = None
    if dns_ok is True:
        out.green(f"DNS: .localchat forwarding to {dns_ip} ✓")
    elif dns_ok is False:
        out.red("DNS: .localchat forwarding NOT configured")
        sub.print("Run:")
        sub.print(f"    sudo resolvectl dns incusbr0 {dns_ip}")
        sub.print("    sudo resolvectl domain incusbr0 ~localchat")
    else:
        sub.print("DNS: .localchat forwarding status UNKNOWN")


# -------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------


def _format_addrs(ip, ipv6=None):
    parts = [f"IPv4 {ip}"]
    if ipv6:
        parts.append(f"IPv6 {ipv6}")
    return ", ".join(parts)


def _deploy_status(ct, local_hash, ix):
    """Return a human-readable deploy status string.

    Compares the full deployed version (hash + diff) against
    the local state built by :func:`~cmdeploy.util.get_version_string`.
    """
    deployed = ct.deployed_version()
    if deployed is None:
        return "NOT DEPLOYED"

    # A container launched from the relay image has the same
    # git hash but a different domain — always redeploy.
    deployed_domain = ct.deployed_domain()
    if deployed_domain and deployed_domain != ct.domain:
        return f"DOMAIN-MISMATCH (deployed: {deployed_domain})"

    deployed_lines = deployed.splitlines()
    deployed_hash = deployed_lines[0] if deployed_lines else ""
    short = deployed_hash[:12]

    if not local_hash:
        return f"UNKNOWN (deployed: {short})"

    local_short = local_hash[:12]
    if deployed_hash != local_hash:
        return f"STALE (deployed: {short}, local: {local_short})"

    # Hash matches — check for uncommitted diffs
    local_version = get_version_string()
    if deployed != local_version:
        return f"DIRTY ({local_short}, undeployed changes)"

    return f"IN-SYNC ({short})"


def _add_name_args(parser, help_text=None):
    """Add optional positional NAME arguments."""
    parser.add_argument(
        "names",
        nargs="*",
        metavar="NAME",
        help=help_text or "Relay name(s) to operate on.",
    )


def _run_cmdeploy(subcmd, ct, ix, out, extra=None, **kwargs):
    """Run ``cmdeploy <subcmd>`` with standard --config/--ssh flags.

    *ct* is a Container (uses ``ct.ini`` and ``ct.domain``).
    Returns the subprocess exit code.
    """
    extra_str = " ".join(extra) if extra else ""
    v_flag = " -" + "v" * out.verbosity if out.verbosity > 0 else ""
    cmd = f"""\
        cmdeploy{v_flag} {subcmd}
        --config {ct.ini}
        --ssh-config {ix.ssh_config_path}
        --ssh-host {ct.domain}
        {extra_str}
    """
    if "cwd" not in kwargs:
        kwargs["cwd"] = str(ix.project_root)
    return out.shell(cmd, **kwargs)
