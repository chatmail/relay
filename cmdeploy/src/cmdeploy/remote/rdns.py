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
        return
    dkim_value_raw = f"v=DKIM1;k=rsa;p={dkim_pubkey};s=email;t=s"
    dkim_value = '" "'.join(re.findall(".{1,255}", dkim_value_raw))
    web_dkim_value = "".join(re.findall(".{1,255}", dkim_value_raw))
    return (
        f'{dkim_selector}._domainkey.{mail_domain}. TXT "{dkim_value}"',
        f'{dkim_selector}._domainkey.{mail_domain}. TXT "{web_dkim_value}"',
    )


def query_dns(typ, domain):
    # Get autoritative nameserver from the SOA record.
    soa_answers = [
        x.split()
        for x in shell(
            f"dig -r -q {domain} -t SOA +noall +authority +answer", print=log_progress
        ).split("\n")
    ]
    soa = [a for a in soa_answers if len(a) >= 3 and a[3] == "SOA"]
    if not soa:
        return
    ns = soa[0][4]

    # Query authoritative nameserver directly to bypass DNS cache.
    res = shell(f"dig @{ns} -r -q {domain} -t {typ} +short", print=log_progress)
    return next((line for line in res.split("\n") if not line.startswith(";")), "")


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
        zf_domain, zf_typ, zf_value = zf_line.split(maxsplit=2)
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
