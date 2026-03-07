"""lxc-start/stop/status/test subcommands for testing with local containers."""

import os
import subprocess
import threading
import time
from contextlib import contextmanager

from ..util import (
    collapse,
    get_git_hash,
    get_version_string,
    shell,
)
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
    ix = Incus()
    out.green("Ensuring DNS container (ns-localchat) ...")
    dns_ct = ix.get_dns_container()
    dns_ct.ensure()
    if not ix.find_dns_image():
        with _section(out, "LXC: publishing DNS image"):
            dns_ct.publish_as_dns_image()
    print(f"  DNS container IP: {dns_ct.ipv4}")

    names = args.names if args.names else RELAY_NAMES
    relays = list(ix.get_container(n) for n in names)
    for ct in relays:
        out.green(f"Ensuring container {ct.name!r} ({ct.domain}) ...")
        ct.ensure()
        ip = ct.ipv4

        print("  Configuring container hostname ...")
        ct.configure_hosts(ip)

        print(f"  Writing {ct.ini.name} ...")
        ct.write_ini(disable_ipv6=args.ipv4_only)
        print(f"  Config: {ct.ini}")
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
        print(f"  {_format_addrs(ip, ipv6)}")

        out.green(f"  Container {ct.name!r} ready: {ct.domain} -> {ip}")
        print()

    # Reset DNS zones only for the containers we just started
    started_cnames = {ct.name for ct in relays}
    managed = ix.list_managed()
    started = [c for c in managed if c["name"] in started_cnames]

    if started:
        print(
            f"Resetting DNS zones for {len(started)} domain(s) (A + AAAA records) ..."
        )
        dns_ct.reset_dns_records(dns_ct.ipv4, started)

        for ct in relays:
            if ct.name in started_cnames:
                print(f"  Configuring DNS in {ct.name} ...")
                ct.configure_dns(dns_ct.ipv4)

    # Generate the unified SSH config
    out.green("Writing ssh-config ...")
    ssh_cfg = ix.write_ssh_config()
    print(f"  {ssh_cfg}")

    # Verify SSH via the generated config
    for ct in relays:
        print(f"  Verifying SSH to {ct.name} via ssh-config ...")
        if ct.verify_ssh(ssh_cfg):
            print(f"  SSH OK: ssh -F lxconfigs/ssh-config {ct.domain}")
        else:
            out.red(f"  WARNING: SSH verification failed for {ct.name}")

    # Print integration suggestions
    ssh_cfg = ix.ssh_config_path
    if not ix.check_ssh_include():
        out.green(
            "\n  (Optional) To use containers from any SSH client, add to ~/.ssh/config:"
        )
        out.green(f"      Include {ssh_cfg}")

    # Optionally run cmdeploy run on each relay
    if args.run:
        for ct in relays:
            with _section(out, f"cmdeploy run: {ct.sname} ({ct.domain})"):
                ret = _run_cmdeploy("run", ct, ix, extra=["--skip-dns-check"])
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
    ix = Incus()
    names = args.names or RELAY_NAMES
    destroy = args.destroy or args.destroy_all

    for ct in map(ix.get_container, names):
        if destroy:
            out.green(f"Destroying container {ct.name!r} ...")
            ct.destroy()
            if hasattr(ct, "image_alias"):
                out.green(f"  Deleting cached image {ct.image_alias!r} ...")
                ix.run(["image", "delete", ct.image_alias], check=False)
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
    ix = Incus()
    t_total = time.time()
    relay_names = list(RELAY_NAMES)
    if args.one:
        relay_names = relay_names[:1]

    local_hash = get_git_hash()

    # Per-relay: start containers, then deploy in parallel.
    ipv4_only_flags = {RELAY_NAMES[0]: False, RELAY_NAMES[1]: True}

    # Phase 1 — start all containers (sequential, fast)
    for ct in map(ix.get_container, relay_names):
        name = ct.sname
        ipv4_only = ipv4_only_flags.get(name, False)
        label = "IPv4-only" if ipv4_only else "dual-stack"

        with _section(out, f"LXC: lxc-start {name} ({label})"):
            args.names = [name]
            args.ipv4_only = ipv4_only
            args.run = False
            ret = lxc_start_cmd(args, out)
            if ret:
                return ret

    # Phase 2 — deploy all relays in parallel
    to_deploy = []
    for ct in map(ix.get_container, relay_names):
        status = _deploy_status(ct, local_hash, ix)
        if "IN-SYNC" in status:
            _section_line(
                out, f"cmdeploy run: {ct.sname} — {status}, skipping"
            )
        else:
            to_deploy.append(ct)

    if to_deploy:
        with _section(out, "cmdeploy run (parallel)"):
            ret = _run_cmdeploy_parallel(
                "run", to_deploy, ix, out, extra=["--skip-dns-check"]
            )
            if ret:
                return ret

    # Phase 3 — publish images (sequential, fast)
    for ct in map(ix.get_container, relay_names):
        if ct.publish_image():
            _section_line(out, f"LXC: published {ct.sname} image")
        else:
            _section_line(
                out,
                f"LXC: publish {ct.sname} image — skipped, cached",
            )

    for ct in map(ix.get_container, relay_names):
        with _section(out, f"cmdeploy dns: {ct.sname} ({ct.domain})"):
            ret = _run_cmdeploy("dns", ct, ix, extra=["--zonefile", str(ct.zone)])
            if ret:
                out.red(f"DNS for {ct.sname} failed (exit {ret})")
                return ret

    with _section(out, "LXC: PowerDNS zone update"):
        dns_ct = ix.get_dns_container()
        for ct in map(ix.get_container, relay_names):
            if ct.zone.exists():
                zone_data = ct.zone.read_text()
                print(f"  Loading {ct.zone} into PowerDNS ...")
                dns_ct.set_dns_records(zone_data)

    # Run tests in both directions when two relays are available.
    test_pairs = [(0, 1), (1, 0)] if len(relay_names) > 1 else [(0,)]
    for pair in test_pairs:
        first = ix.get_container(relay_names[pair[0]])
        label = first.sname
        env = None
        if len(pair) > 1:
            second = ix.get_container(relay_names[pair[1]])
            label = f"{first.sname} \u2194 {second.sname}"
            env = os.environ.copy()
            env["CHATMAIL_DOMAIN2"] = second.domain

        with _section(out, f"cmdeploy test: {label}"):
            ret = _run_cmdeploy("test", first, ix, **({"env": env} if env else {}))
            if ret:
                out.red(f"Tests failed (exit {ret})")
                return ret

    elapsed = time.time() - t_total
    _section_line(out, f"lxc-test complete ({elapsed:.1f}s)")
    return 0


# -------------------------------------------------------------------
# lxc-status
# -------------------------------------------------------------------


def lxc_status_cmd_options(parser):
    pass


def lxc_status_cmd(args, out):
    """Show status of local LXC chatmail containers."""
    ix = Incus()
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
    if storage_path:
        out.green(f"Containers: ({storage_path})")
    else:
        out.green("Containers:")

    dns_ip = None
    for c in containers:
        _print_container_status(c, ix, local_hash)
        if c["name"] == ix.get_dns_container().name:
            dns_ip = c["ip"]

    _print_ssh_status(out, ix)
    _print_dns_forwarding_status(out, dns_ip)
    return 0


def _print_container_status(c, ix, local_hash):
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
    print(f"  {cname:20s} {tag}")

    # Second line: domain, IPv4, IPv6
    domain = c.get("domain", "")
    ip = c.get("ip") or "?"
    ipv6 = c.get("ipv6")
    print(f"  {domain:20s} {_format_addrs(ip, ipv6)}")

    # Third line: RAM (RSS), config
    indent = " " * 21
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

    print(f"  {indent}{detail}")
    print()


def _print_ssh_status(out, ix):
    """Print SSH integration status."""
    print()
    ssh_cfg = ix.ssh_config_path
    if ix.check_ssh_include():
        out.green("SSH: ~/.ssh/config includes lxconfigs/ssh-config ✓")
    else:
        out.red("SSH: ~/.ssh/config does NOT include lxconfigs/ssh-config")
        print("  Add to ~/.ssh/config:")
        print(f"      Include {ssh_cfg}")


def _print_dns_forwarding_status(out, dns_ip):
    """Print host DNS forwarding status for .localchat."""
    if not dns_ip:
        out.red("DNS: ns-localchat container not found")
        return
    try:
        rv = shell("resolvectl status incusbr0", timeout=5)
        dns_ok = dns_ip in rv.stdout and "localchat" in rv.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        dns_ok = None
    if dns_ok is True:
        out.green(f"DNS: .localchat forwarding to {dns_ip} ✓")
    elif dns_ok is False:
        out.red("DNS: .localchat forwarding NOT configured")
        print("  Run:")
        print(f"      sudo resolvectl dns incusbr0 {dns_ip}")
        print("      sudo resolvectl domain incusbr0 ~localchat")
    else:
        print("  DNS: .localchat forwarding status UNKNOWN")


# -------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------


def _format_addrs(ip, ipv6=None):
    parts = [f"IPv4 {ip}"]
    if ipv6:
        parts.append(f"IPv6 {ipv6}")
    return ", ".join(parts)


SECTION_WIDTH = 72


@contextmanager
def _section(out, title):
    bar = "\u2501" * (SECTION_WIDTH - len(title) - 5)
    out.green(f"\u2501\u2501\u2501 {title} {bar}")
    t0 = time.time()
    yield
    elapsed = time.time() - t0
    print(f"{'':>{SECTION_WIDTH - 10}}({elapsed:.1f}s)")
    print()


def _section_line(out, title):
    bar = "\u2501" * (SECTION_WIDTH - len(title) - 5)
    out.green(f"\u2501\u2501\u2501 {title} {bar}")
    print()


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


def _build_cmdeploy_cmd(subcmd, ct, ix, extra=None):
    """Build the ``cmdeploy <subcmd>`` command string."""
    extra_str = " ".join(extra) if extra else ""
    return collapse(f"""\
        cmdeploy {subcmd}
        --config {ct.ini}
        --ssh-config {ix.ssh_config_path}
        --ssh-host {ct.domain}
        {extra_str}
    """)


def _run_cmdeploy(subcmd, ct, ix, extra=None, **kwargs):
    """Run ``cmdeploy <subcmd>`` with standard --config/--ssh flags.

    *ct* is a Container (uses ``ct.ini`` and ``ct.domain``).
    Returns the subprocess exit code.
    """
    cmd = _build_cmdeploy_cmd(subcmd, ct, ix, extra=extra)
    if "cwd" not in kwargs:
        kwargs["cwd"] = str(ix.project_root)
    print(f"  [$ {cmd}]")
    return shell(cmd, capture_output=False, **kwargs).returncode


# Number of tail lines to print on failure.
_FAIL_CONTEXT_LINES = 40


def _run_cmdeploy_parallel(subcmd, containers, ix, out, extra=None):
    """Run ``cmdeploy <subcmd>`` for every container in parallel.

    Output is captured and filtered: only lines containing
    ``"Start operation"`` are printed (prefixed with the relay
    short-name).  On failure the last *_FAIL_CONTEXT_LINES*
    lines of that process's output are shown.
    """
    procs = []  # list of (container, Popen, collected_lines)
    cwd = str(ix.project_root)

    for ct in containers:
        cmd = _build_cmdeploy_cmd(subcmd, ct, ix, extra=extra)
        print(f"  [{ct.sname}] $ {cmd}")
        proc = subprocess.Popen(
            cmd,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=cwd,
        )
        procs.append((ct, proc, []))

    def _reader(ct, proc, lines):
        prefix = f"  [{ct.sname}]"
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            lines.append(line)
            if "Starting operation" in line:
                print(f"{prefix} {line}")

    threads = []
    for ct, proc, lines in procs:
        t = threading.Thread(
            target=_reader, args=(ct, proc, lines), daemon=True,
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join()
    for _, proc, _ in procs:
        proc.wait()

    # Check results
    first_failure = 0
    for ct, proc, lines in procs:
        if proc.returncode:
            out.red(
                f"Deploy to {ct.sname} failed "
                f"(exit {proc.returncode})"
            )
            tail = lines[-_FAIL_CONTEXT_LINES:]
            for tl in tail:
                print(f"  [{ct.sname}] {tl}")
            if not first_failure:
                first_failure = proc.returncode

    return first_failure
