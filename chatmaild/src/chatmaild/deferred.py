"""
Analyze deferred mails and print most common failing destinations.

Example:

    python -m chatmaild.deferred
"""

import json
import subprocess
from collections import Counter, defaultdict


def main():
    p = subprocess.Popen(["postqueue", "-j"], text=True, stdout=subprocess.PIPE)
    domain_reasons = defaultdict(Counter)
    domain_total = Counter()

    for line in p.stdout:
        item = json.loads(line)
        if item["queue_name"] != "deferred":
            continue

        for recipient in item["recipients"]:
            _, domain = recipient["address"].rsplit("@", 1)
            reason = recipient["delay_reason"]
            domain_total[domain] += 1
            domain_reasons[domain][reason] += 1

    for domain, total in reversed(domain_total.most_common()):
        print(f"{domain} ({total} recipients)")
        for reason, count in domain_reasons[domain].most_common():
            print(f"  {count}: {reason}")


if __name__ == "__main__":
    main()
