"""
Pure python functions which execute remotely in a system Python interpreter.

All functions of this module

- need to get and and return Python builtin data types only,

- can only use standard library dependencies,

- can freely call each other.
"""

import re

from .rshell import CalledProcessError, log_progress, shell


def perform_initial_checks(mail_domain, pre_command=""):
    """Collecting initial DNS settings."""
    assert mail_domain
    if not shell("dig", fail_ok=True, print=log_progress):
        shell("apt-get update && apt-get install -y dnsutils", print=log_progress)
    A = query_dns("A", mail_domain)
    AAAA = query_dns("AAAA", mail_domain)
    MTA_STS = query_dns("CNAME", f"mta-sts.{mail_domain}")
    WWW = query_dns("CNAME", f"www.{mail_domain}")

    res = dict(mail_domain=mail_domain, A=A, AAAA=AAAA, MTA_STS=MTA_STS, WWW=WWW)
    res["acme_account_url"] = shell(
        pre_command + "acmetool account-url", fail_ok=True, print=log_progress
    )
    res["dkim_entry"], res["web_dkim_entry"] = get_dkim_entry(
        mail_domain, pre_command, dkim_selector="opendkim"
    )

    if not MTA_STS or not WWW or (not A and not AAAA):
        return res

    # parse out sts-id if exists, example: "v=STSv1; id=2090123"
    mta_sts_txt = query_dns("TXT", f"_mta-sts.{mail_domain}")
    if not mta_sts_txt:
        return res
    parts = mta_sts_txt.split("id=")
    res["sts_id"] = parts[1].rstrip('"') if len(parts) == 2 else ""
    return res


def get_dkim_entry(mail_domain, pre_command, dkim_selector):
    try:
        dkim_pubkey = shell(
            f"{pre_command}openssl rsa -in /etc/dkimkeys/{dkim_selector}.private "
            "-pubout 2>/dev/null | awk '/-/{next}{printf(\"%s\",$0)}'",
            print=log_progress,
        )
    except CalledProcessError:
        return None, None
    dkim_value_raw = f"v=DKIM1;k=rsa;p={dkim_pubkey};s=email;t=s"
    dkim_value = '" "'.join(re.findall(".{1,255}", dkim_value_raw))
    web_dkim_value = "".join(re.findall(".{1,255}", dkim_value_raw))
    name = f"{dkim_selector}._domainkey.{mail_domain}."
    return (
        f'{name:<40} 3600   IN  TXT    "{dkim_value}"',
        f'{name:<40} 3600   IN  TXT    "{web_dkim_value}"',
    )


def query_dns(typ, domain, shell_exec=None):
    if shell_exec is None:
        shell_exec = shell
    # Get autoritative nameserver from the SOA record.
    soa_answers = [
        x.split()
        for x in shell_exec(
            f"dig -r -q {domain} -t SOA +noall +authority +answer", print=log_progress
        ).split("\n")
    ]
    soa = [a for a in soa_answers if len(a) >= 3 and a[3] == "SOA"]
    if not soa:
        return
    ns = soa[0][4]

    # Query authoritative nameserver directly to bypass DNS cache.
    return _dig_authoritative(ns, domain, typ, shell_exec=shell_exec)


def _parse_dig_result(output):
    """Return first non-comment, non-empty line from dig output, or empty string."""
    lines = [line for line in output.split("\n") if not line.startswith(";")]
    return next((line for line in lines if line.strip()), "")


def _dig_authoritative(ns, domain, typ, shell_exec=None):
    """Query authoritative NS, falling back to IPv4-only if default fails."""
    if shell_exec is None:
        shell_exec = shell

    # limit timeout and tries to not hang on a broken default NS
    cmd = f"dig @{ns} -r -q {domain} -t {typ} +short +timeout=10 +tries=2"
    result = _parse_dig_result(shell_exec(cmd, print=log_progress))
    if result:
        return result
    # Fallback: force IPv4 transport (handles broken IPv6 to NS)
    return _parse_dig_result(shell_exec(cmd + " -4", print=log_progress))


def check_zonefile(zonefile, verbose=True):
    """Check expected zone file entries."""
    required = True
    required_diff = []
    recommended_diff = []

    for zf_line in zonefile.splitlines():
        if "; Recommended" in zf_line:
            required = False
            continue
        if not zf_line.strip() or zf_line.startswith(";"):
            continue
        print(f"dns-checking {zf_line!r}") if verbose else log_progress("")
        zf_domain, _ttl, _in, zf_typ, zf_value = zf_line.split(None, 4)
        zf_domain = zf_domain.rstrip(".")
        zf_value = zf_value.strip()
        query_value = query_dns(zf_typ, zf_domain)
        if zf_value != query_value:
            assert zf_typ in ("A", "AAAA", "CNAME", "CAA", "SRV", "MX", "TXT"), zf_line
            if required:
                required_diff.append(zf_line)
            else:
                recommended_diff.append(zf_line)

    return required_diff, recommended_diff
