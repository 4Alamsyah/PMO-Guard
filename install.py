"""Usage (Administrator prompt):
    python install.py install | uninstall | restart        (pywin32 service)
    python install.py install-nssm | uninstall-nssm       (via NSSM)
"""
import ctypes
import json
import os
import shutil
import subprocess
import sys

NAME = "PMOGuard"
SRC = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), NAME)
FILES = ["common.py", "agent.py", "service.py"]


def run(*args, check=True):
    print(">", " ".join(args))
    return subprocess.run(list(args), cwd=APP if os.path.isdir(APP) else None, check=check)


def install():
    os.makedirs(APP, exist_ok=True)
    for f in FILES:
        shutil.copy2(os.path.join(SRC, f), os.path.join(APP, f))
    cfg = os.path.join(APP, "config.json")
    if not os.path.exists(cfg):                       # never overwrite the user's list
        shutil.copy2(os.path.join(SRC, "config.default.json"), cfg)
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    with open(os.path.join(APP, "runtime.json"), "w", encoding="utf-8") as f:
        json.dump({"pythonw": pythonw}, f)
    svc = os.path.join(APP, "service.py")
    run(sys.executable, svc, "--startup", "auto", "install")
    run("sc", "failure", NAME, "reset=", "86400", "actions=",
        "restart/5000/restart/5000/restart/5000")
    run(sys.executable, svc, "start")
    print("Installed. Edit %s to change the block list." % cfg)


def install_nssm():
    """Same app, but registered through NSSM (nssm.exe must be on PATH)."""
    if not shutil.which("nssm"):
        sys.exit("nssm.exe not found on PATH. Download from https://nssm.cc and add it to PATH.")
    os.makedirs(APP, exist_ok=True)
    for f in FILES + ["launcher.py"]:
        shutil.copy2(os.path.join(SRC, f), os.path.join(APP, f))
    cfg = os.path.join(APP, "config.json")
    if not os.path.exists(cfg):
        shutil.copy2(os.path.join(SRC, "config.default.json"), cfg)
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    with open(os.path.join(APP, "runtime.json"), "w", encoding="utf-8") as f:
        json.dump({"pythonw": pythonw}, f)
    run("nssm", "install", NAME, sys.executable, os.path.join(APP, "launcher.py"))
    run("nssm", "set", NAME, "AppDirectory", APP)
    run("nssm", "set", NAME, "DisplayName", "PMO Guard Service")
    run("nssm", "set", NAME, "Start", "SERVICE_AUTO_START")
    run("nssm", "set", NAME, "AppExit", "Default", "Restart")
    run("nssm", "set", NAME, "AppRestartDelay", "5000")
    run("nssm", "set", NAME, "AppStopMethodConsole", "3000")
    run("nssm", "start", NAME)
    print("Installed via NSSM. Edit %s to change the block list." % cfg)


def uninstall_nssm():
    run("nssm", "stop", NAME, check=False)
    run("nssm", "remove", NAME, "confirm", check=False)
    sys.path.insert(0, APP)
    try:
        from common import sync_hosts
        sync_hosts([])
    except Exception as e:
        print("hosts cleanup failed:", e)
    shutil.rmtree(APP, ignore_errors=True)
    print("Removed.")


def uninstall():
    svc = os.path.join(APP, "service.py")
    run(sys.executable, svc, "stop", check=False)
    run(sys.executable, svc, "remove", check=False)
    sys.path.insert(0, APP)
    try:
        from common import sync_hosts
        sync_hosts([])
    except Exception as e:
        print("hosts cleanup failed:", e)
    shutil.rmtree(APP, ignore_errors=True)
    print("Removed.")


if __name__ == "__main__":
    if not ctypes.windll.shell32.IsUserAnAdmin():
        sys.exit("Run this from an Administrator prompt.")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "install":
        install()
    elif cmd == "uninstall":
        uninstall()
    elif cmd == "install-nssm":
        install_nssm()
    elif cmd == "uninstall-nssm":
        uninstall_nssm()
    elif cmd == "restart":
        run(sys.executable, os.path.join(APP, "service.py"), "restart")
    else:
        sys.exit(__doc__)
