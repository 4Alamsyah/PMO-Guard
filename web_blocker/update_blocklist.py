"""Downloads the Blocklist Project's maintained adult-content domain list and
merges it with your manual blocklist.txt into blocklist_auto.txt.

Source: https://github.com/blocklistproject/Lists (MIT licensed, community maintained)

Run this any time you want to refresh from upstream:
    python update_blocklist.py
"""
import os
import re
import urllib.request

import blocklist_loader

SOURCE_URL = "https://raw.githubusercontent.com/blocklistproject/Lists/master/porn.txt"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MANUAL_PATH = os.path.join(SCRIPT_DIR, "blocklist.txt")
AUTO_PATH = os.path.join(SCRIPT_DIR, "blocklist_auto.txt")

HOSTS_LINE_RE = re.compile(r"^0\.0\.0\.0\s+(\S+)")


def fetch_domains(url):
    req = urllib.request.Request(url, headers={"User-Agent": "personal-web-blocker"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8", errors="ignore")

    domains = set()
    for line in text.splitlines():
        m = HOSTS_LINE_RE.match(line.strip())
        if m:
            domains.add(m.group(1).lower())
    return domains


def main():
    print(f"Fetching {SOURCE_URL} ...")
    remote = fetch_domains(SOURCE_URL)
    print(f"Fetched {len(remote):,} domains from upstream.")

    manual = set(blocklist_loader.load_blocklist(MANUAL_PATH)) if os.path.exists(MANUAL_PATH) else set()
    combined = sorted(remote | manual)

    with open(AUTO_PATH, "w", encoding="utf-8") as f:
        f.write(f"# Auto-generated from {SOURCE_URL}\n")
        f.write("# Regenerate any time with: python update_blocklist.py\n")
        f.write("# Add your OWN extra domains to blocklist.txt instead - this file gets overwritten.\n")
        for d in combined:
            f.write(d + "\n")

    print(f"Wrote {len(combined):,} domains to {AUTO_PATH}")


if __name__ == "__main__":
    main()
