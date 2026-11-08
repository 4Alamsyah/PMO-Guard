"""Shared helpers: config, matcher, logging, hosts-file sync."""
import json
import os
import re
import time

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")      # admin-only (Program Files)
RUNTIME_PATH = os.path.join(APP_DIR, "runtime.json")
DATA_DIR = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "PMOGuard")
LOG_PATH = os.path.join(DATA_DIR, "events.log")
HOSTS_PATH = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                          r"System32\drivers\etc\hosts")
# Manual list of PersonalWebBlocker (DNS layer). Its domains are merged into block_domains
# so the keyboard/title layer keeps working when a VPN bypasses the DNS layer.
WEB_BLOCKER_LIST = r"E:\Claude\web_blocker\blocklist.txt"

DEFAULTS = {
    "message": "Stop. Kamu sudah berkomitmen berhenti. Tarik napas, berdiri, minum air, lakukan hal lain.",
    "action": "close_tab",            # close_tab | alert_only
    "browsers": ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
                 "opera.exe", "vivaldi.exe"],
    "check_title": True,
    "title_poll_seconds": 1.0,
    "buffer_size": 80,
    "cooldown_seconds": 3,
    "lock_after_hits": 3,
    "lock_window_seconds": 600,
    "block_words": [],
    "block_contains": [],
    "block_domains": [],
}


def read_domain_file(path):
    """One domain per line, '#' comments. Missing file -> empty list."""
    try:
        with open(path, encoding="utf-8") as f:
            return [ln.strip().lower() for ln in f
                    if ln.strip() and not ln.strip().startswith("#")]
    except Exception:
        return []


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            user = json.load(f)
    except Exception:
        user = {}
    cfg = dict(DEFAULTS)
    cfg.update(user)
    cfg["block_domains"] = list(cfg["block_domains"]) + read_domain_file(WEB_BLOCKER_LIST)
    return cfg


def log(line):
    """Event log. Never writes what was typed, only source + matched rule."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), line))
    except Exception:
        pass


class Matcher:
    """block_words    -> whole-word match (no letters/digits around it)
       block_contains -> plain substring match
       block_domains  -> substring match on the domain's first label (or full domain if short)"""

    def __init__(self, cfg):
        self.rules = []
        for w in cfg["block_words"]:
            w = w.lower().strip()
            if w:
                self.rules.append((w, re.compile(
                    r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])")))
        subs = [s.lower().strip() for s in cfg["block_contains"]]
        for d in cfg["block_domains"]:
            d = d.lower().strip()
            base = d.split(".")[0]
            subs.append(base if len(base) >= 5 else d)
        for s in subs:
            if s:
                self.rules.append((s, re.compile(re.escape(s))))

    def match(self, text):
        text = text.lower()
        for label, rx in self.rules:
            if rx.search(text):
                return label
        return None


BEGIN = "# >>> PMOGuard BEGIN"
END = "# <<< PMOGuard END"


def sync_hosts(domains):
    """Keep a managed block in the hosts file. Empty list removes it."""
    try:
        with open(HOSTS_PATH, "r", encoding="latin-1", newline="") as f:
            text = f.read()
    except Exception:
        return
    lines = text.splitlines()
    out, skip = [], False
    for ln in lines:
        if ln.strip() == BEGIN:
            skip = True
            continue
        if ln.strip() == END:
            skip = False
            continue
        if not skip:
            out.append(ln)
    while out and not out[-1].strip():
        out.pop()
    if domains:
        out.append("")
        out.append(BEGIN)
        for d in sorted({x.lower().strip() for x in domains if x.strip()}):
            for host in (d, "www." + d):
                out.append("0.0.0.0 " + host)
                out.append(":: " + host)
        out.append(END)
    new = "\r\n".join(out) + "\r\n"
    if new == text:
        return
    try:
        with open(HOSTS_PATH, "w", encoding="latin-1", newline="") as f:
            f.write(new)
    except Exception as e:
        log("hosts sync failed: %r" % (e,))
