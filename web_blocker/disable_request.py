"""Step 1 of disabling the blocker: starts a cool-down timer.

This is a commitment device, not a security boundary — the point is to give
your future self a mandatory pause instead of an instant off switch.
Run confirm_disable.py after the delay to actually remove the service.
"""
import json
import os
import time

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "disable_request.json")
DELAY_MINUTES = 30  # change this if you want a longer/shorter cool-down


def main():
    ready_at = time.time() + DELAY_MINUTES * 60
    with open(STATE_FILE, "w") as f:
        json.dump({"ready_at": ready_at}, f)
    print(f"Disable requested. Run confirm_disable.py in {DELAY_MINUTES} minutes to finish.")
    print("If you don't run confirm_disable.py, nothing happens — the blocker keeps running.")


if __name__ == "__main__":
    main()
