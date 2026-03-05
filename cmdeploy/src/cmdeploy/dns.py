import datetime

from . import remote


def parse_zone_records(text):
    """Yield ``(name, ttl, rtype, rdata)`` from standard BIND-format text.

    Skips comment lines (starting with ``;``) and blank lines.
    Each record line must have the format ``name TTL IN type rdata``.
    """
    for raw_line in text.strip().splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        parts = line.split(None, 4)
        if len(parts) < 5:
            raise ValueError(f"Bad zone record line: {line}")
        name = parts[0].rstrip(".")
        # parts[2] is the IN class — ignored
        yield name, parts[1], parts[3].upper(), parts[4]


def get_initial_remote_data(sshexec, mail_domain):
    return sshexec.logged(
        call=remote.rdns.perform_initial_checks, kwargs=dict(mail_domain=mail_domain)
    )


def check_initial_remote_data(remote_data, *, strict_tls=True, print=print):
    mail_domain = remote_data["mail_domain"]
    if not remote_data["A"] and not remote_data["AAAA"]:
        print(f"Missing A and/or AAAA DNS records for {mail_domain}!")
    elif strict_tls and remote_data["MTA_STS"] != f"{mail_domain}.":
        print("Missing MTA-STS CNAME record:")
        print(f"mta-sts.{mail_domain}.   CNAME  {mail_domain}.")
    elif strict_tls and remote_data["WWW"] != f"{mail_domain}.":
        print("Missing www CNAME record:")
        print(f"www.{mail_domain}.   CNAME  {mail_domain}.")
    else:
        return remote_data


def get_filled_zone_file(remote_data):
    sts_id = remote_data.get("sts_id")
    if not sts_id:
        remote_data["sts_id"] = datetime.datetime.now().strftime("%Y%m%d%H%M")

    d = remote_data["mail_domain"]
    lines = ["; Required DNS entries"]
    if remote_data.get("A"):
        lines.append(f"{d}.  3600  IN  A  {remote_data['A']}")
    if remote_data.get("AAAA"):
        lines.append(f"{d}.  3600  IN  AAAA  {remote_data['AAAA']}")
    lines.append(f"{d}.  3600  IN  MX  10 {d}.")
    if remote_data.get("strict_tls"):
        lines.append(
            f'_mta-sts.{d}.  3600  IN  TXT  "v=STSv1; id={remote_data["sts_id"]}"'
        )
        lines.append(f"mta-sts.{d}.  3600  IN  CNAME  {d}.")
    lines.append(f"www.{d}.  3600  IN  CNAME  {d}.")
    lines.append(remote_data["dkim_entry"])
    lines.append("")
    lines.append("; Recommended DNS entries")
    lines.append(f'{d}.  3600  IN  TXT  "v=spf1 a ~all"')
    lines.append(f'_dmarc.{d}.  3600  IN  TXT  "v=DMARC1;p=reject;adkim=s;aspf=s"')
    if remote_data.get("acme_account_url"):
        lines.append(
            f"{d}.  3600  IN  CAA  0 issue"
            f' "letsencrypt.org;accounturi={remote_data["acme_account_url"]}"'
        )
    lines.append(f'_adsp._domainkey.{d}.  3600  IN  TXT  "dkim=discardable"')
    lines.append(f"_submission._tcp.{d}.  3600  IN  SRV  0 1 587 {d}.")
    lines.append(f"_submissions._tcp.{d}.  3600  IN  SRV  0 1 465 {d}.")
    lines.append(f"_imap._tcp.{d}.  3600  IN  SRV  0 1 143 {d}.")
    lines.append(f"_imaps._tcp.{d}.  3600  IN  SRV  0 1 993 {d}.")
    lines.append("")
    return "\n".join(lines)


def check_full_zone(sshexec, remote_data, out, zonefile) -> int:
    """Check existing DNS records, optionally write them to zone file
    and return (exitcode, remote_data) tuple."""

    required_diff, recommended_diff = sshexec.logged(
        remote.rdns.check_zonefile,
        kwargs=dict(zonefile=zonefile, verbose=False),
    )

    returncode = 0
    if required_diff:
        out.red("Please set required DNS entries at your DNS provider:\n")
        for line in required_diff:
            out(line)
        out("")
        returncode = 1
    if remote_data.get("dkim_entry") in required_diff:
        out(
            "If the DKIM entry above does not work with your DNS provider, you can try this one:\n"
        )
        out(remote_data.get("web_dkim_entry") + "\n")
    if recommended_diff:
        out("WARNING: these recommended DNS entries are not set:\n")
        for line in recommended_diff:
            out(line)

    if not (recommended_diff or required_diff):
        out.green("Great! All your DNS entries are verified and correct.")
    return returncode
