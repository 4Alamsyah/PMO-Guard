"""NSSM entry point: plain watchdog loop (NSSM turns it into a service running as SYSTEM).

Keeps agent.py alive in the active user session and keeps the hosts block in place.
Needs: pip install pywin32 (only for the WTS / CreateProcessAsUser APIs).
"""
import json
import os
import signal
import sys
import time

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

import pywintypes
import win32con
import win32process
import win32profile
import win32security
import win32ts

from common import RUNTIME_PATH, load_config, log, sync_hosts

STILL_ACTIVE = 259
proc, session, started_at, next_try = None, None, 0.0, 0.0
running = True


def launch_agent():
    sid = win32ts.WTSGetActiveConsoleSessionId()
    if sid in (0, 0xFFFFFFFF):
        return None, None
    try:
        token = win32ts.WTSQueryUserToken(sid)
    except pywintypes.error:
        return None, None
    primary = win32security.DuplicateTokenEx(
        token, win32security.SecurityImpersonation, win32con.MAXIMUM_ALLOWED,
        win32security.TokenPrimary)
    env = win32profile.CreateEnvironmentBlock(primary, False)
    with open(RUNTIME_PATH, encoding="utf-8") as f:
        pythonw = json.load(f)["pythonw"]
    si = win32process.STARTUPINFO()
    si.lpDesktop = "winsta0\\default"
    cmd = '"%s" "%s"' % (pythonw, os.path.join(APP_DIR, "agent.py"))
    hproc, hthread, _p, _t = win32process.CreateProcessAsUser(
        primary, None, cmd, None, None, False,
        win32con.CREATE_NO_WINDOW | win32con.CREATE_UNICODE_ENVIRONMENT,
        env, APP_DIR, si)
    hthread.Close()
    return hproc, sid


def alive():
    return proc is not None and win32process.GetExitCodeProcess(proc) == STILL_ACTIVE


def ensure_agent():
    global proc, session, started_at, next_try
    sid = win32ts.WTSGetActiveConsoleSessionId()
    if alive() and sid == session:
        return
    now = time.time()
    if proc and not alive() and now - started_at < 10:
        next_try = now + 30                      # died instantly (duplicate?) -> back off
    if proc and alive():
        win32process.TerminateProcess(proc, 0)
    if proc:
        proc.Close()
        proc = None
    if now < next_try:
        return
    try:
        proc, session = launch_agent()
        started_at = now
        log("agent launched session=%s" % (session,))
    except Exception as e:
        log("launch failed: %r" % (e,))
        next_try = now + 15


def stop(*_):
    global running
    running = False


def main():
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, stop)
    log("launcher started")
    last_hosts = 0.0
    while running:
        ensure_agent()
        if time.time() - last_hosts > 60:
            last_hosts = time.time()
            sync_hosts(load_config()["block_domains"])
        time.sleep(3)
    if alive():
        win32process.TerminateProcess(proc, 0)
    log("launcher stopped")


if __name__ == "__main__":
    main()
