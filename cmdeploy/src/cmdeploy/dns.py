import requests

url = "https://dns.nextdns.io/dns-query"
dns_types = {
    "A": 1,
    "AAAA": 28,
    "CNAME": 5,
    "MX": 15,
    "SRV": 33,
    "CAA": 257,
    "TXT": 16,
}


class DNS:
    def __init__(self):
        self.session = requests.Session()

    def get(self, typ: str, domain: str) -> str:
        """Get a DNS entry"""
        r = self.session.get(
            url,
            params={"name": domain, "type": typ},
            headers={"accept": "application/dns-json"},
        )

        j = r.json()
        if "Answer" in j:
            for answer in j["Answer"]:
                if answer["type"] == dns_types[typ]:
                    return answer["data"]
        return ""

    def resolve_mx(self, domain: str) -> (str, str):
        """Resolve an MX entry"""
        r = self.session.get(
            url,
            params={"name": domain, "type": "MX"},
            headers={"accept": "application/dns-json"},
        )

        j = r.json()
        if "Answer" in j:
            result = (0, None)
            for answer in j["Answer"]:
                if answer["type"] == dns_types["MX"]:
                    prio, server_name = answer["data"].split()
                    if int(prio) > result[0]:
                        result = (int(prio), server_name)
            return result
        return None, None

    def resolve(self, domain: str) -> str:
        result = self.get("A", domain)
        if not result:
            result = self.get("CNAME", domain)
            if result:
                result = self.get("A", result[:-1])
                if not result:
                    result = self.get("AAAA", domain)
        return result
