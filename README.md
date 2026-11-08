# PMO Guard

A two-layer accountability toolkit for a personal Windows PC. It is made of two cooperating Windows services:

| Component | Folder | What it does |
|---|---|---|
| **PMO Guard** (`PMOGuard`) | repo root | Watches keystrokes and window titles in browsers, closes matching tabs, and locks the PC after repeated hits. Works regardless of network, so it still applies when a VPN is on. |
| **Personal Web Blocker** (`PersonalWebBlocker`) | `web_blocker/` | Local DNS resolver that blocks a large domain list across all browsers, plus a browser DNS-over-HTTPS lockdown. |

The two layers cover each other's gaps: the DNS blocker stops blocked sites at the network level, and PMO Guard catches what the DNS layer misses (for example, when a VPN bypasses it). PMO Guard also reads the manual list in `web_blocker/blocklist.txt` and keeps the Web Blocker service running.

## Architecture

```
PMOGuard service (SYSTEM, auto-start, auto-restart)
 ├─ launches and keeps the agent running in the active user session
 ├─ keeps the hosts-file block for block_domains in place
 └─ every 30 s: restarts PersonalWebBlocker if it was stopped
                (skipped while a disable cool-down is pending)

agent.py (user session)
 ├─ low-level keyboard hook (WH_KEYBOARD_LL), active only when a browser is foreground
 ├─ 80-character in-memory buffer (never written to disk or sent anywhere)
 ├─ second layer: polls the browser window title every second (catches clicked links / pasted URLs)
 └─ on match: Ctrl+W (close tab) + message; 3 hits within 10 minutes -> lock the PC

PersonalWebBlocker service (LocalSystem, auto-start, auto-restart)
 ├─ DNS resolver on 127.0.0.1 / ::1: NXDOMAIN for blocked domains, forwards the rest to 1.1.1.3 (Cloudflare Family)
 └─ re-applies browser DoH-off policy keys every 5 seconds
```

Why two processes for PMO Guard: services run in Session 0 and cannot hook the user's keyboard, so the agent runs in the user session and is launched by the service.

## Requirements

- Windows 10/11
- Python 3.11 (other 3.x versions should work)
- Administrator rights for installation
- `pip install pywin32 dnspython`

## Install

Run all commands from an **Administrator** prompt.

**1. Personal Web Blocker (DNS layer)**

```
cd web_blocker
pip install -r requirements.txt
python update_blocklist.py      # optional: downloads ~950k domains into blocklist_auto.txt
python install.py
```

Then point Windows at the local resolver (this step is manual because it changes network settings):

- Settings → Network & Internet → your connection → Edit DNS settings → Manual
- IPv4: Preferred `127.0.0.1`, Alternate `1.1.1.3`
- IPv6: Preferred `::1`, Alternate `2606:4700:4700::1113`

Check status any time with `python blocker_service.py status`.

**2. PMO Guard (keyboard / title layer)**

```
pip install pywin32
python install.py install        # from the repo root
```

- Block list: `C:\Program Files\PMOGuard\config.json` (admin only). Changes are picked up automatically; hosts entries sync every 60 seconds.
- Event log: `C:\ProgramData\PMOGuard\events.log` (records the source and matched rule only, never the typed text).
- Uninstall: `python install.py uninstall`

An alternative install via NSSM is available with `python install.py install-nssm` (requires `nssm.exe` on PATH).

## Configuration

PMO Guard `config.json`:

- `block_words`: whole-word match (safe for short words).
- `block_contains`: substring match.
- `block_domains`: blocked in the hosts file and matched while typing or in titles. Entries from `web_blocker/blocklist.txt` are merged in automatically.
- `action`: `close_tab` or `alert_only`.
- `check_title`: set to `false` if you get too many false positives.

Personal Web Blocker lists:

- `web_blocker/blocklist.txt`: your manual entries, one domain per line. Re-read automatically.
- `web_blocker/blocklist_auto.txt`: generated from the Blocklist Project list. Do not edit by hand; regenerate with `update_blocklist.py`.

### Path dependency

PMO Guard reads the manual list from a fixed path defined in `common.py`:

```python
WEB_BLOCKER_LIST = r"E:\Claude\web_blocker\blocklist.txt"
```

If you move the `web_blocker` folder, update this constant and reinstall PMO Guard. The watchdog uses the same folder to find `disable_request.json`.

## Disabling

Both components are deliberately annoying to turn off:

1. `python web_blocker/disable_request.py` starts a 30-minute cool-down.
2. After the cool-down, run `python web_blocker/confirm_disable.py` (Administrator) to remove the Web Blocker service.

While `disable_request.json` exists, PMO Guard's watchdog does not restart the Web Blocker, so the cool-down flow works as intended. If you never run `confirm_disable.py`, delete `disable_request.json` to re-enable the watchdog.

Remove the DNS setting, DoH registry keys, and PMO Guard manually as described in `web_blocker/README.md` if you want a full clean-up.

## Limitations

These are real and worth knowing:

- **VPN and DNS.** A VPN that sets its own DNS or routes traffic outside the PC bypasses the DNS layer. PMO Guard still catches typed text and matching window titles. If you use Cloudflare WARP, enable its built-in "1.1.1.1 for Families" mode so filtering continues inside the tunnel.
- **Coverage of PMO Guard.** It only sees browsers in its `browsers` list, and only text you type or window titles. Links opened from other apps, portable browsers, non-browser apps, and phones are not covered.
- **Administrator access.** Anyone with admin rights on the PC can stop or remove both services. The intended setup is a standard Windows account for daily use, with the admin password held by an accountability partner.
- **Safe Mode or booting another OS** skips both services.
- **Port 53 conflicts.** If another local program (a VPN client, Docker, another DNS tool) already listens on port 53, the resolver may fail to start. Check with `python blocker_service.py debug`.
- **Network-level blocking is not complete on every adapter.** Adapters still using the router's DNS bypass the local resolver. Set DNS on every active adapter that should be filtered.

Use this as a strong speed bump for your own account, not as an unbreakable lock. For a boundary that survives admin access, filter at the router (for example, Cloudflare Family DNS) and use a separate non-admin account for daily use.

## Intended use

Install only on a PC you own, or with the consent of its owner.
