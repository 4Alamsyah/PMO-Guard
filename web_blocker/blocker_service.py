"""Windows Service: runs the local blocking DNS resolver + re-applies the
browser DoH policy lockdown every few seconds so tampering gets reverted.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import win32serviceutil
import win32service
import win32event
import servicemanager

import blocklist_loader
import doh_policy
import dns_server

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BLOCKLIST_MANUAL = os.path.join(SCRIPT_DIR, "blocklist.txt")
BLOCKLIST_AUTO = os.path.join(SCRIPT_DIR, "blocklist_auto.txt")
CHECK_INTERVAL_SECONDS = 5


class WebBlockerService(win32serviceutil.ServiceFramework):
    _svc_name_ = "PersonalWebBlocker"
    _svc_display_name_ = "Personal Web Blocker"
    _svc_description_ = "Local DNS-based website blocker with browser DoH policy lockdown."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.running = True
        self.dns_servers = []
        self.store = dns_server.BlocklistStore()
        self._last_mtimes = (0, 0)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.running = False
        for srv in self.dns_servers:
            srv.shutdown()
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        self.main()

    def _reload_if_changed(self):
        m1 = os.path.getmtime(BLOCKLIST_MANUAL) if os.path.exists(BLOCKLIST_MANUAL) else 0
        m2 = os.path.getmtime(BLOCKLIST_AUTO) if os.path.exists(BLOCKLIST_AUTO) else 0
        if (m1, m2) == self._last_mtimes:
            return
        domains = set()
        if os.path.exists(BLOCKLIST_MANUAL):
            domains |= set(blocklist_loader.load_blocklist(BLOCKLIST_MANUAL))
        if os.path.exists(BLOCKLIST_AUTO):
            domains |= set(blocklist_loader.load_blocklist(BLOCKLIST_AUTO))
        self.store.set_domains(domains)
        self._last_mtimes = (m1, m2)

    def main(self):
        self._reload_if_changed()
        self.dns_servers = dns_server.start_servers(self.store, log=servicemanager.LogErrorMsg)

        while self.running:
            try:
                doh_policy.apply_doh_lockdown()
                self._reload_if_changed()
            except Exception as e:
                servicemanager.LogErrorMsg(f"WebBlocker error: {e}")

            rc = win32event.WaitForSingleObject(self.hWaitStop, CHECK_INTERVAL_SECONDS * 1000)
            if rc == win32event.WAIT_OBJECT_0:
                break


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(WebBlockerService)
