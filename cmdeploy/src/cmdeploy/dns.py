import datetime

from . import remote


def parse_zone_records(text):
    """Yield ``(name, ttl, rtype, rdata)`` from standard BIND-format text."""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        try:
            name, ttl, _in, rtype, rdata = line.split(None, 4)
        except ValueError:
            raise ValueError(f"Bad zone record line: {line!r}") from None
        name = name.rstrip(".")
        yield name, ttl, rtype.upper(), rdata


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

    def append_record(name, rtype, rdata, ttl=3600):
        lines.append(f"{name:<40} {ttl:<6} IN  {rtype:<5}  {rdata}")

    lines = ["; Required DNS entries"]
    if remote_data.get("A"):
        append_record(f"{d}.", "A", remote_data["A"])
    if remote_data.get("AAAA"):
        append_record(f"{d}.", "AAAA", remote_data["AAAA"])
    append_record(f"{d}.", "MX", f"10 {d}.")
    if remote_data.get("strict_tls"):
        append_record(f"_mta-sts.{d}.", "TXT", f'"v=STSv1; id={remote_data["sts_id"]}"')
        append_record(f"mta-sts.{d}.", "CNAME", f"{d}.")
    append_record(f"www.{d}.", "CNAME", f"{d}.")
    lines.append(remote_data["dkim_entry"])
    lines.append("")
    lines.append("; Recommended DNS entries")
    append_record(f"{d}.", "TXT", '"v=spf1 a ~all"')
    append_record(f"_dmarc.{d}.", "TXT", '"v=DMARC1;p=reject;adkim=s;aspf=s"')
    if remote_data.get("acme_account_url"):
        append_record(
            f"{d}.",
            "CAA",
            f'0 issue "letsencrypt.org;accounturi={remote_data["acme_account_url"]}"',
        )
    append_record(f"_adsp._domainkey.{d}.", "TXT", '"dkim=discardable"')
    append_record(f"_submission._tcp.{d}.", "SRV", f"0 1 587 {d}.")
    append_record(f"_submissions._tcp.{d}.", "SRV", f"0 1 465 {d}.")
    append_record(f"_imap._tcp.{d}.", "SRV", f"0 1 143 {d}.")
    append_record(f"_imaps._tcp.{d}.", "SRV", f"0 1 993 {d}.")
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
            "If the DKIM entry above does not work with your DNS provider,"
            " you can try this one:\n"
        )
        out(remote_data.get("web_dkim_entry") + "\n")
    if recommended_diff:
        out("WARNING: these recommended DNS entries are not set:\n")
        for line in recommended_diff:
            out(line)

    if not (recommended_diff or required_diff):
        out.green("Great! All your DNS entries are verified and correct.")
    return returncode
