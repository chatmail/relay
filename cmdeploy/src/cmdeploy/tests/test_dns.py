from copy import deepcopy

import pytest

from cmdeploy import remote
from cmdeploy.dns import check_full_zone, check_initial_remote_data


@pytest.fixture
def mockdns_base(monkeypatch):
    qdict = {}

    def shell(command, fail_ok=False, print=print):
        if command.startswith("dig"):
            if command == "dig":
                return "."
            if "SOA" in command:
                return (
                    "delta.chat. 21600 IN SOA ns1.first-ns.de. dns.hetzner.com."
                    " 2025102800 14400 1800 604800 3600"
                )
            command_chunks = command.split()
            domain, typ = command_chunks[4], command_chunks[6]
            try:
                return qdict[typ][domain]
            except KeyError:
                return ""
        return remote.rshell.shell(command=command, fail_ok=fail_ok, print=print)

    monkeypatch.setattr(remote.rdns, shell.__name__, shell)
    return qdict


@pytest.fixture
def mockdns_expected():
    return {
        "A": {"some.domain": "1.1.1.1"},
        "AAAA": {"some.domain": "fde5:cd7a:9e1c:3240:5a99:936f:cdac:53ae"},
        "CNAME": {
            "mta-sts.some.domain": "some.domain.",
            "www.some.domain": "some.domain.",
        },
    }


@pytest.fixture(params=["plain", "with-dns-comments"])
def mockdns(request, mockdns_base, mockdns_expected):
    mockdns_base.update(deepcopy(mockdns_expected))
    match request.param:
        case "plain":
            pass
        case "with-dns-comments":
            for typ, data in mockdns_base.items():
                for host, result in data.items():
                    mockdns_base[typ][host] = (
                        ";; some unsuccessful attempt result\n"
                        "; and another with a single semicolon\n"
                        f"{result}"
                    )
    return mockdns_base


class TestPerformInitialChecks:
    def test_perform_initial_checks_ok1(self, mockdns, mockdns_expected):
        remote_data = remote.rdns.perform_initial_checks("some.domain")
        assert remote_data["A"] == mockdns_expected["A"]["some.domain"]
        assert remote_data["AAAA"] == mockdns_expected["AAAA"]["some.domain"]
        assert (
            remote_data["MTA_STS"] == mockdns_expected["CNAME"]["mta-sts.some.domain"]
        )
        assert remote_data["WWW"] == mockdns_expected["CNAME"]["www.some.domain"]

    @pytest.mark.parametrize("drop", ["A", "AAAA"])
    def test_perform_initial_checks_with_one_of_A_AAAA(self, mockdns, drop):
        del mockdns[drop]
        remote_data = remote.rdns.perform_initial_checks("some.domain")
        assert not remote_data[drop]

        l = []
        res = check_initial_remote_data(remote_data, print=l.append)
        assert res
        assert not l

    def test_perform_initial_checks_no_mta_sts(self, mockdns):
        del mockdns["CNAME"]["mta-sts.some.domain"]
        remote_data = remote.rdns.perform_initial_checks("some.domain")
        assert not remote_data["MTA_STS"]

        l = []
        res = check_initial_remote_data(remote_data, print=l.append)
        assert not res
        assert len(l) == 2


def parse_zonefile_into_dict(zonefile, mockdns_base, only_required=False):
    for zf_line in zonefile.split("\n"):
        if zf_line.startswith("#"):
            if "Recommended" in zf_line and only_required:
                return
            continue
        if not zf_line.strip():
            continue
        zf_domain, zf_typ, zf_value = zf_line.split(maxsplit=2)
        zf_domain = zf_domain.rstrip(".")
        zf_value = zf_value.strip()
        mockdns_base.setdefault(zf_typ, {})[zf_domain] = zf_value


class MockSSHExec:
    def logged(self, func, kwargs):
        return func(**kwargs)

    def call(self, func, kwargs):
        return func(**kwargs)


class TestZonefileChecks:
    def test_check_zonefile_all_ok(self, cm_data, mockdns_base):
        zonefile = cm_data.get("zftest.zone")
        parse_zonefile_into_dict(zonefile, mockdns_base)
        required_diff, recommended_diff = remote.rdns.check_zonefile(zonefile)
        assert not required_diff and not recommended_diff

    def test_check_zonefile_recommended_not_set(self, cm_data, mockdns_base):
        zonefile = cm_data.get("zftest.zone")
        zonefile_mocked = zonefile.split("; Recommended")[0]
        parse_zonefile_into_dict(zonefile_mocked, mockdns_base)
        required_diff, recommended_diff = remote.rdns.check_zonefile(zonefile)
        assert not required_diff
        assert len(recommended_diff) == 8

    def test_check_zonefile_output_required_fine(self, cm_data, mockdns_base, mockout):
        zonefile = cm_data.get("zftest.zone")
        zonefile_mocked = zonefile.split("; Recommended")[0]
        parse_zonefile_into_dict(zonefile_mocked, mockdns_base, only_required=True)
        mssh = MockSSHExec()
        mockdns_base["mail_domain"] = "some.domain"
        res = check_full_zone(mssh, mockdns_base, out=mockout, zonefile=zonefile)
        assert res == 0
        assert "WARNING" in mockout.captured_plain[0]
        assert len(mockout.captured_plain) == 9

    def test_check_zonefile_output_full(self, cm_data, mockdns_base, mockout):
        zonefile = cm_data.get("zftest.zone")
        parse_zonefile_into_dict(zonefile, mockdns_base)
        mssh = MockSSHExec()
        mockdns_base["mail_domain"] = "some.domain"
        res = check_full_zone(mssh, mockdns_base, out=mockout, zonefile=zonefile)
        assert res == 0
        assert not mockout.captured_red
        assert "correct" in mockout.captured_green[0]
        assert not mockout.captured_red
