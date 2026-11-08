"""PMO Guard Windows service (runs as SYSTEM).

Jobs:
  1. Keep the agent alive inside the active user session (relaunch if killed / on new logon).
  2. Keep the hosts-file block for block_domains in place.
"""
import json
import os
import sys
import time

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

import pywintypes
import servicemanager
import win32con
import win32event
import win32process
import win32profile
import win32security
import win32service
import win32serviceutil
import win32ts

from common import RUNTIME_PATH, WEB_BLOCKER_LIST, load_config, log, sync_hosts

STILL_ACTIVE = 259
BLOCKER_SERVICE = "PersonalWebBlocker"
BLOCKER_DIR = os.path.dirname(WEB_BLOCKER_LIST)
BLOCKER_CHECK_SECONDS = 30


def ensure_blocker():
    """Restart PersonalWebBlocker if it was stopped. Skipped while its disable cool-down is pending."""
    if os.path.exists(os.path.join(BLOCKER_DIR, "disable_request.json")):
        return
    try:
        state = win32serviceutil.QueryServiceStatus(BLOCKER_SERVICE)[1]
        if state == win32service.SERVICE_STOPPED:
            win32serviceutil.StartService(BLOCKER_SERVICE)
            log("restarted %s" % BLOCKER_SERVICE)
    except Exception as e:
        log("blocker check failed: %r" % (e,))


def launch_agent():
    sid = win32ts.WTSGetActiveConsoleSessionId()
    if sid in (0, 0xFFFFFFFF):
        return None, None
    try:
        token = win32ts.WTSQueryUserToken(sid)
    except pywintypes.error:
        return None, None                       # nobody logged in yet
    primary = win32security.DuplicateTokenEx(
        token, win32security.SecurityImpersonation, win32con.MAXIMUM_ALLOWED,
        win32security.TokenPrimary)
    env = win32profile.CreateEnvironmentBlock(primary, False)
    with open(RUNTIME_PATH, encoding="utf-8") as f:
        pythonw = json.load(f)["pythonw"]
    si = win32process.STARTUPINFO()
    si.lpDesktop = "winsta0\\default"
    cmd = '"%s" "%s"' % (pythonw, os.path.join(APP_DIR, "agent.py"))
    hproc, hthread, _pid, _tid = win32process.CreateProcessAsUser(
        primary, None, cmd, None, None, False,
        win32con.CREATE_NO_WINDOW | win32con.CREATE_UNICODE_ENVIRONMENT,
        env, APP_DIR, si)
    hthread.Close()
    return hproc, sid


class PMOGuardService(win32serviceutil.ServiceFramework):
    _svc_name_ = "PMOGuard"
    _svc_display_name_ = "PMO Guard Service"
    _svc_description_ = "Accountability tool: blocks access to harmful sites based on browser input."

    def __init__(self, args):
        super().__init__(args)
        self.stop_evt = win32event.CreateEvent(None, 0, 0, None)
        self.proc = None
        self.session = None
        self.started_at = 0.0
        self.next_try = 0.0

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_evt)

    def alive(self):
        if not self.proc:
            return False
        return win32process.GetExitCodeProcess(self.proc) == STILL_ACTIVE

    def ensure_agent(self):
        sid = win32ts.WTSGetActiveConsoleSessionId()
        if self.alive() and sid == self.session:
            return
        now = time.time()
        if self.proc and not self.alive() and now - self.started_at < 10:
            self.next_try = now + 30            # exits instantly (e.g. duplicate) -> back off
        if self.proc and sid != self.session and self.alive():
            win32process.TerminateProcess(self.proc, 0)
        if self.proc:
            self.proc.Close()
            self.proc = None
        if now < self.next_try:
            return
        try:
            self.proc, self.session = launch_agent()
            self.started_at = now
        except Exception as e:
            log("launch failed: %r" % (e,))
            self.next_try = now + 15

    def SvcDoRun(self):
        servicemanager.LogInfoMsg("PMOGuard started")
        last_hosts = last_blocker = 0.0
        while win32event.WaitForSingleObject(self.stop_evt, 3000) != win32event.WAIT_OBJECT_0:
            self.ensure_agent()
            if time.time() - last_blocker > BLOCKER_CHECK_SECONDS:
                last_blocker = time.time()
                ensure_blocker()
            if time.time() - last_hosts > 60:
                last_hosts = time.time()
                sync_hosts(load_config()["block_domains"])
        if self.alive():
            win32process.TerminateProcess(self.proc, 0)
        servicemanager.LogInfoMsg("PMOGuard stopped")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(PMOGuardService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(PMOGuardService)
