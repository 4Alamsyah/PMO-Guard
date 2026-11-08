"""Shared helper for reading a domain-per-line blocklist text file."""


def load_blocklist(path):
    with open(path, "r", encoding="utf-8") as f:
        return [ln.strip().lower() for ln in f if ln.strip() and not ln.strip().startswith("#")]
