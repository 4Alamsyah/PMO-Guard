"""Installs and starts the PersonalWebBlocker Windows Service. Run as Administrator."""
import ctypes
import os
import subprocess
import sys


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def main():
    if not is_admin():
        print("This script must be run as Administrator. Right-click your terminal -> 'Run as administrator'.")
        sys.exit(1)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    service_script = os.path.join(script_dir, "blocker_service.py")

    subprocess.run([sys.executable, service_script, "--startup", "auto", "install"], check=True)

    # Auto-restart the service if it's ever killed/crashed.
    subprocess.run(
        [
            "sc", "failure", "PersonalWebBlocker",
            "reset=", "0",
            "actions=", "restart/5000/restart/5000/restart/5000",
        ],
        check=True,
    )

    subprocess.run([sys.executable, service_script, "start"], check=True)
    print("PersonalWebBlocker installed, set to auto-start, and running.")
    print("It re-applies the browser DoH lockdown every 5 seconds, so tampering self-heals.")
    print()
    print("One more manual step required: point this PC's DNS at the local resolver.")
    print("See README.md 'Point Windows at the local resolver' section.")


if __name__ == "__main__":
    main()
