"""Step 2 of disabling the blocker: only works after the cool-down from disable_request.py has elapsed.

Stops and removes the Windows Service. Run as Administrator.
Note: hosts file entries and browser registry policies are left in place after this —
see README.md for how to remove those manually if you want a full clean-up.
"""
import ctypes
import json
import os
import subprocess
import sys
import time

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "disable_request.json")


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def main():
    if not is_admin():
        print("This script must be run as Administrator.")
        sys.exit(1)

    if not os.path.exists(STATE_FILE):
        print("No pending disable request. Run disable_request.py first, then wait out the cool-down.")
        sys.exit(1)

    with open(STATE_FILE) as f:
        data = json.load(f)

    remaining = data["ready_at"] - time.time()
    if remaining > 0:
        mins = int(remaining // 60) + 1
        print(f"Not yet — {mins} more minute(s) left in the cool-down.")
        sys.exit(1)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    service_script = os.path.join(script_dir, "blocker_service.py")
    subprocess.run([sys.executable, service_script, "stop"], check=False)
    subprocess.run([sys.executable, service_script, "remove"], check=True)
    os.remove(STATE_FILE)
    print("Service stopped and removed.")
    print("Your DNS settings still point at 127.0.0.1 and browser DoH policy keys are still set —")
    print("see README.md 'Turning it off' section to revert both.")


if __name__ == "__main__":
    main()
