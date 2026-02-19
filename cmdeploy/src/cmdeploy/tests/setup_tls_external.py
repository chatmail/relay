"""Setup and verify external TLS certificates for a chatmail server.

Generates a self-signed TLS certificate, uploads it to the chatmail
server via SCP, runs ``cmdeploy run``, and then probes all TLS-enabled
ports (nginx, postfix, dovecot) to verify the certificate is actually
served.  After probing, checks remote service logs for errors.

Prerequisites
~~~~~~~~~~~~~
- SSH root access to the target server (same as ``cmdeploy run``)
- ``cmdeploy`` in PATH (activate the venv first)

How to run
~~~~~~~~~~
From the repository root::

    # Full run: generate cert, deploy, probe ports, check services
    python -m cmdeploy.tests.setup_tls_external DOMAIN

    # Re-probe only (after a previous deploy)
    python -m cmdeploy.tests.setup_tls_external DOMAIN \\
        --skip-deploy --skip-certgen

    # Override SSH host (e.g. when domain doesn't resolve to the server)
    python -m cmdeploy.tests.setup_tls_external DOMAIN \\
        --ssh-host staging-ipv4.testrun.org

Arguments
~~~~~~~~~
DOMAIN            mail domain for the chatmail server (SSH root login must work)

Options
~~~~~~~
--skip-deploy     skip ``cmdeploy run``, only probe ports
--skip-certgen    skip cert generation/upload, use certs already on server
--ssh-host HOST   SSH host override (defaults to DOMAIN)
"""

import argparse
import shutil
import smtplib
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Cert paths on the remote server
REMOTE_CERT = "/etc/ssl/certs/tmp_fullchain.pem"
REMOTE_KEY = "/etc/ssl/private/tmp_privkey.pem"


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------


def generate_config(domain: str, config_dir: Path) -> Path:
    """Generate a chatmail.ini with tls_external_cert_and_key for *domain*."""
    from chatmaild.config import write_initial_config

    ini_path = config_dir / "chatmail.ini"
    write_initial_config(
        ini_path,
        domain,
        overrides={
            "tls_external_cert_and_key": f"{REMOTE_CERT} {REMOTE_KEY}",
        },
    )
    print(f"[+] Generated chatmail.ini for {domain} in {config_dir}")
    return ini_path


# ---------------------------------------------------------------------------
# Certificate generation
# ---------------------------------------------------------------------------


def generate_cert(domain: str, cert_dir: Path) -> tuple:
    """Generate a self-signed TLS cert+key for *domain* with proper SANs."""
    from cmdeploy.selfsigned.deployer import openssl_selfsigned_args

    cert_path = cert_dir / "fullchain.pem"
    key_path = cert_dir / "privkey.pem"
    subprocess.check_call(openssl_selfsigned_args(domain, cert_path, key_path, days=30))
    print(f"[+] Generated cert for {domain} in {cert_dir}")
    return cert_path, key_path


# ---------------------------------------------------------------------------
# Upload certs to remote server
# ---------------------------------------------------------------------------


def upload_certs(
    ssh_host: str,
    cert_path: Path,
    key_path: Path,
) -> None:
    """SCP cert and key to the remote server."""
    subprocess.check_call([
        "scp", str(cert_path), f"root@{ssh_host}:{REMOTE_CERT}",
    ])
    subprocess.check_call([
        "scp", str(key_path), f"root@{ssh_host}:{REMOTE_KEY}",
    ])
    # Ensure cert is world-readable and key is readable by ssl-cert group
    # (dovecot/postfix/nginx need to read these files)
    subprocess.check_call([
        "ssh", f"root@{ssh_host}",
        f"chmod 644 {REMOTE_CERT} && chmod 640 {REMOTE_KEY}"
        f" && chgrp ssl-cert {REMOTE_KEY}",
    ])
    print(f"[+] Uploaded cert/key to {ssh_host}")


# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------


def run_deploy(ini_path: str) -> None:
    """Run ``cmdeploy run --skip-dns-check --config <ini>``."""
    cmd = ["cmdeploy", "run", "--config", str(ini_path), "--skip-dns-check"]
    print(f"[+] Running: {' '.join(cmd)}")
    subprocess.check_call(cmd)
    print("[+] Deploy completed successfully")


# ---------------------------------------------------------------------------
# TLS port probing
# ---------------------------------------------------------------------------


def get_peer_cert_binary(host: str, port: int) -> bytes:
    """Connect to host:port with TLS and return the DER-encoded peer cert."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=15) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ssock:
            return ssock.getpeercert(binary_form=True)


def get_smtp_starttls_cert_binary(host: str, port: int = 587) -> bytes:
    """Connect via SMTP STARTTLS and return the DER cert."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.starttls(context=ctx)
        return smtp.sock.getpeercert(binary_form=True)


def check_cert_matches(
    label: str, served_der: bytes, expected_der: bytes,
) -> bool:
    """Compare served DER cert against the expected cert."""
    if served_der == expected_der:
        print(f"  [OK]   {label}: certificate matches")
        return True
    else:
        print(f"  [FAIL] {label}: certificate does NOT match")
        return False


def load_cert_der(cert_pem_path: Path) -> bytes:
    """Load a PEM cert file and return its DER encoding."""
    pem_text = cert_pem_path.read_text()
    start = pem_text.index("-----BEGIN CERTIFICATE-----")
    end = pem_text.index("-----END CERTIFICATE-----") + len(
        "-----END CERTIFICATE-----"
    )
    return ssl.PEM_cert_to_DER_cert(pem_text[start:end])


def probe_all_ports(host: str, expected_cert_der: bytes) -> bool:
    """Probe TLS ports and verify the served certificate matches.

    Checks ports 993 (IMAP), 465 (SMTPS), 587 (STARTTLS), and 443
    (nginx stream).  Port 8443 is skipped as nginx binds it to
    localhost behind the stream proxy on 443.
    """
    print(f"\n[+] Probing TLS ports on {host}...")
    all_ok = True

    for label, port in [
        ("IMAP/TLS (993)", 993),
        ("SMTP/TLS (465)", 465),
    ]:
        try:
            served = get_peer_cert_binary(host, port)
            if not check_cert_matches(label, served, expected_cert_der):
                all_ok = False
        except Exception as e:
            print(f"  [FAIL] {label}: connection failed: {e}")
            all_ok = False

    # STARTTLS on port 587
    try:
        served = get_smtp_starttls_cert_binary(host, 587)
        if not check_cert_matches("SMTP/STARTTLS (587)", served, expected_cert_der):
            all_ok = False
    except Exception as e:
        print(f"  [FAIL] SMTP/STARTTLS (587): connection failed: {e}")
        all_ok = False

    # Port 443 (nginx stream proxy with ALPN routing)
    try:
        served = get_peer_cert_binary(host, 443)
        if not check_cert_matches("nginx/443 (stream)", served, expected_cert_der):
            all_ok = False
    except Exception as e:
        print(f"  [FAIL] nginx/443 (stream): connection failed: {e}")
        all_ok = False

    return all_ok


# ---------------------------------------------------------------------------
# Post-deploy service health checks
# ---------------------------------------------------------------------------

SERVICES = ["dovecot", "postfix", "nginx"]


def check_remote_services(ssh_host: str, since: str = "") -> bool:
    """SSH to the server and check for service failures or errors.

    *since* is a ``journalctl --since`` timestamp (e.g. ``"5 min ago"``).
    If empty, checks the entire boot journal.
    """
    print(f"\n[+] Checking remote service health on {ssh_host}...")
    all_ok = True

    for svc in SERVICES:
        try:
            result = subprocess.run(
                ["ssh", f"root@{ssh_host}",
                 f"systemctl is-active {svc}.service"],
                capture_output=True, text=True, timeout=15, check=False,
            )
            status = result.stdout.strip()
            if status == "active":
                print(f"  [OK]   {svc}: active")
            else:
                print(f"  [FAIL] {svc}: {status}")
                all_ok = False
        except Exception as e:
            print(f"  [FAIL] {svc}: check failed: {e}")
            all_ok = False

    return all_ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "domain",
        help="mail domain (SSH root login must work to this host)",
    )
    parser.add_argument(
        "--skip-deploy",
        action="store_true",
        help="skip cmdeploy run, only probe ports",
    )
    parser.add_argument(
        "--skip-certgen",
        action="store_true",
        help="skip cert generation and upload (use existing)",
    )
    parser.add_argument(
        "--ssh-host",
        help="SSH host override (defaults to DOMAIN)",
    )
    args = parser.parse_args()

    domain = args.domain
    ssh_host = args.ssh_host or domain
    print(f"[+] Domain: {domain}")
    print(f"[+] SSH host: {ssh_host}")
    print(f"[+] Remote cert: {REMOTE_CERT}")
    print(f"[+] Remote key:  {REMOTE_KEY}")

    work_dir = Path(tempfile.mkdtemp(prefix="tls-external-test-"))
    try:
        # Generate chatmail.ini
        ini_path = generate_config(domain, work_dir)

        if not args.skip_certgen:
            local_cert, local_key = generate_cert(domain, work_dir)
            upload_certs(ssh_host, local_cert, local_key)
        else:
            local_cert = work_dir / "fullchain.pem"
            subprocess.check_call([
                "scp", f"root@{ssh_host}:{REMOTE_CERT}", str(local_cert),
            ])

        # Record timestamp before deploy for journal filtering
        deploy_start = time.strftime("%Y-%m-%d %H:%M:%S")

        if not args.skip_deploy:
            run_deploy(ini_path)

        # Probe TLS ports
        expected_der = load_cert_der(local_cert)
        ports_ok = probe_all_ports(domain, expected_der)

        # Check service health (only errors since deploy started)
        services_ok = check_remote_services(ssh_host, since=deploy_start)

        if ports_ok and services_ok:
            print(
                "\n[SUCCESS] All TLS port probes passed and services are healthy"
            )
            return 0
        else:
            if not ports_ok:
                print("\n[FAILURE] Some TLS port probes failed", file=sys.stderr)
            if not services_ok:
                print(
                    "\n[FAILURE] Some services have errors", file=sys.stderr
                )
            return 1
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
