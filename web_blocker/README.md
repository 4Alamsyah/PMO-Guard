# Personal Web Blocker

Blocks a large list of domains across **every browser** on this Windows
machine using two mechanisms together:

1. **A local DNS resolver** (`dns_server.py`) — a tiny DNS server that runs
   on `127.0.0.1` (and `::1`). It answers `NXDOMAIN` for any blocked domain
   or subdomain, and transparently forwards everything else to Cloudflare
   Family DNS (`1.1.1.3` — malware **and adult content**) upstream. This
   forwarding step matters as much as the local list: it's a live,
   continuously-updated category database run by Cloudflare, not something
   we maintain — so a brand-new adult site that isn't in our downloaded
   list yet still gets caught here. (Note: `1.1.1.2` is a different,
   malware-only address — using it by mistake silently lets adult sites
   through, which is what `1.1.1.3` fixes.) The local list on top of that
   is what lets this scale: it currently has **~950,000 domains**, which a
   Windows hosts file cannot handle without causing serious DNS/network
   slowdowns — a local resolver handles a set that size instantly.
2. **Browser DoH policy lockdown** (`doh_policy.py`) — sets the official
   Chrome/Edge/Brave/Firefox enterprise registry policy to disable
   DNS-over-HTTPS. Without this, a browser can just resolve domains itself
   over DoH and skip your PC's DNS settings entirely — this closes that
   bypass at the source.

Both are re-applied every 5 seconds by a Windows Service, so if the registry
keys get reverted, that's undone within seconds.

## Setup

1. Install dependencies (as Administrator):
   ```
   pip install -r requirements.txt
   ```
2. Install and start the service (as Administrator):
   ```
   python install.py
   ```
3. **Point Windows at the local resolver** — this step is manual because it
   touches your network adapter settings:
   - Settings → Network & Internet → your connection → **Edit DNS settings**
   - Set to **Manual**
   - IPv4 — **Preferred DNS**: `127.0.0.1` · **Alternate DNS**: `1.1.1.3`
   - IPv6 — **Preferred DNS**: `::1` · **Alternate DNS**: `2606:4700:4700::1113`
   - Save

   Why the Alternate DNS is `1.1.1.3` (Cloudflare Family — malware + adult
   content, **not** `1.1.1.2` which is malware-only) instead of a plain open
   resolver: if the local service is ever down, Windows falls back to
   Alternate after a short timeout — this way the fallback still filters
   adult content, not a fully open one.
4. Check status any time:
   ```
   python blocker_service.py status
   ```

The service auto-starts on boot and auto-restarts within 5 seconds if it
crashes or is killed (configured via `sc failure` in `install.py`).

## Updating the blocklist

Two files, merged automatically by the running service (checked every 5s,
no restart needed):

- **`blocklist.txt`** — your own manual entries, one domain per line.
- **`blocklist_auto.txt`** — auto-generated, do not hand-edit. Refresh it
  from the upstream Blocklist Project list any time:
  ```
  python update_blocklist.py
  ```
  This re-downloads the current list (~950k domains) and merges in
  whatever you've added to `blocklist.txt`.

## Turning it off (on purpose)

No instant off switch, by design — that's the point for self-control use.
Two steps with a mandatory 30-minute cool-down between them:

```
python disable_request.py      # starts the timer
# ...wait 30 minutes...
python confirm_disable.py      # as Administrator, removes the service
```

Change `DELAY_MINUTES` in `disable_request.py` for a longer/shorter
cool-down. After `confirm_disable.py`, finish the cleanup manually:

- **DNS settings**: Settings → Network & Internet → Edit DNS settings →
  set back to **Automatic (DHCP)**.
- **Registry**: delete these keys (Win+R → `regedit`):
  - `HKLM\SOFTWARE\Policies\Google\Chrome` → value `DnsOverHttpsMode`
  - `HKLM\SOFTWARE\Policies\Microsoft\Edge` → value `DnsOverHttpsMode`
  - `HKLM\SOFTWARE\Policies\BraveSoftware\Brave` → value `DnsOverHttpsMode`
  - `HKLM\SOFTWARE\Policies\Mozilla\Firefox\DNSOverHTTPS` (whole key)

## Honest limitations

This raises real, meaningful friction, but it isn't unbreakable — you have
Administrator rights on your own PC, and no personal-use tool can fully
close that off:

- **Changing the DNS settings back manually** (step 3 above, in reverse) is
  the direct bypass. The service can't stop you from opening Network
  Settings — it only re-heals the registry/DoH side, not the adapter's DNS
  fields. If you want that step to also require the 30-minute cool-down,
  the honest move is behavioral: don't memorize the steps, or better, use
  a separate non-admin Windows account for daily use so you can't reach
  these settings at all in the moment.
- **Booting Safe Mode / another OS** (e.g. a USB Linux stick) skips
  everything here, since the service never starts.
- **Port 53 conflicts**: if something else on this PC already listens on
  port 53 (a VPN client, Docker, another local DNS tool), the local
  resolver may fail to bind — check with `python blocker_service.py debug`
  or Event Viewer if browsing seems unaffected after setup.
- **A VPN client (e.g. Cloudflare WARP)** takes over system-level routing
  and DNS when connected, bypassing the local resolver entirely — same
  problem as DoH but one level up. If you use WARP, switch it to its own
  built-in **"1.1.1.1 for Families — Block Malware and Adult Content"**
  mode (in the WARP app's Settings) so filtering continues inside the WARP
  tunnel instead of being silently skipped. That covers WARP-on time; the
  local resolver here covers WARP-off time.
- **A phone hotspot or any other device** is obviously unaffected — this
  only controls this PC.
- **Reinstalling Windows** or restoring a backup image removes everything.

If you want a boundary that survives your own admin access on this machine,
the effective move is filtering at the **router** instead (Cloudflare
Family DNS set on the router itself) combined with a separate, non-admin
Windows account for daily use. This tool is best thought of as a strong
speed bump for your admin account, not a lock with no key.
