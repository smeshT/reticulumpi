# g90 image state (snapshotted 2026-07-07, updated 2026-07-08)

This folder is a **portable snapshot** of the g90 box's
"image state" — the configuration files that were edited
or installed on top of the stock g90digi image. It exists
so that, when the remote g90 Pi comes back online, the
same edits can be reapplied to a fresh flash without
having to re-derive them.

The **shared launcher** (Flask app, port **8090** — the wifi clients' home page) lives in
the **parent** of this folder. It is a git clone of this repo,
NOT a direct copy. The full architecture is documented in
`memory/g90-project.md`.

The **node-portal** (Flask app, port **80** — the wifi
setup / admin page) is the inverse role: the page you
reach when you need to fix the network, not the one you
bookmark for daily use. Port :80 binds via
`AmbientCapabilities=CAP_NET_BIND_SERVICE` in
node-portal's systemd unit (not in this image — it's
provided by the g90digi base image). **The shared
launcher was on :80 until commit `a461f3b` (waterfall
tool, 2026-07-09), when it was flipped to :8090 to
avoid colliding with node-portal on :80.** See
`memory/2026-07-19-g90-port-80-incident.md` for the
crash-loop postmortem; fix is in commit `b80a0a1`
(explicit `Environment=LAUNCHER_PORT=8090` in
`g90-shared-launcher.service`).

## Deploy pattern (git-based, as of 2026-07-08)

The workspace at `/home/pi/.openclaw/workspace/g90-shared-launcher/`
is a git working tree. The bare repo at
`/home/pi/repos/reticulumpi.git` is the central pull
target. Each g90 is a clone of that bare repo.

```bash
# 1. Commit your changes in the workspace
cd /home/pi/.openclaw/workspace/g90-shared-launcher
git add -A
git commit -m "Description of the change"
git push origin master

# 2. The g90 boxes pull the new code via the Update button
#    on the launcher's bottom row. That button calls
#    POST /update-from-server which runs:
#    cd /home/pi/shared_launcher && git pull --ff-only
#    sudo systemctl restart g90-shared-launcher.service
```

## First-time setup on a fresh g90 image

```bash
# On the g90 (after a fresh flash + firstboot):

# 1. Clone this repo
sudo -A -u pi git clone https://github.com/smeshT/reticulumpi.git /home/pi/shared_launcher
sudo chown -R pi:pi /home/pi/shared_launcher

# 2. Install the systemd unit
sudo cp /home/pi/shared_launcher/g90-shared-launcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now g90-shared-launcher.service

# 3. Copy the g90-image/ contents into place (only the
#    files the g90 image's firstboot didn't set up itself):
#    - config/reticulumhf-config.env -> /etc/reticulumhf/config.env
#    - config/hostapd.conf -> /etc/hostapd/hostapd.conf
#    - config/pat-config.json -> /home/pi/.config/pat/config.json
#    - config/askpass-g90.sh -> /home/pi/.local/bin/askpass-g90.sh
#    - config/start-novnc-session -> /usr/local/bin/start-novnc-session
#    - systemd-units/pat-http.service -> /etc/systemd/system/
#    - patmenu2-edits/start-pat-ardop -> /home/pi/patmenu2/start-pat-ardop
```

## What's in this folder

### `QUICK-START.md`
A printable one-page guide for the new owner of the
g90 box.

### `node-portal/` and `node-portal-templates/`
- `node-portal/app.py` — the wifi setup Flask app on port **80** (the home page). The port assignment is at the bottom of the file in `app.run(...)`. **Was 8090 until commit `a461f3b` (2026-07-09) flipped it to 80, the inverse of what the launcher's port flip did.**
- `node-portal-templates/` — Jinja templates for the wifi page (index.html), the apps page (apps.html), and an old wifi template (wifi.html).

### `config/`
- `pat-config.json` — pat Winlink config (N0CALL stub)
- `askpass-g90.sh` — g90 askpass wrapper (TEMPLATE — fill in real password at deploy time, NEVER commit a real password)
- `reticulumhf-config.env` — ReticulumHF service config
- `hostapd.conf` — wifi AP config (SSID, channel, etc.)
- `start-novnc-session` — script that brings up Xvfb + openbox + x11vnc

### `systemd-units/`
- `g90-shared-launcher.service` — the shared launcher on port **8090**. `Environment=LAUNCHER_PORT=8090` is set explicitly in the unit (commit `b80a0a1`) so the unit file is the single source of truth for the port; the default in `app.py` is a fallback.
- `pat-http.service` — pat Winlink web UI (port 5000)

### `patmenu2-edits/`
`start-pat-ardop` modified to call
`curl -X POST http://127.0.0.1:80/start-pat-http` instead
of `sudo systemctl restart pat@$USER`.

## When the offline g90 comes online

The dev Pi uses separate per-box askpass wrappers at `~/.local/bin/askpass-<boxname>.sh` that read from `~/.ssh/.<boxname>-pass`. **No real password is ever committed to this repo.** Group-specific credentials (passwords, SSIDs, ZT network IDs) belong in the `smeshT/g90digi` repo (private, group-only), not here.
## Per-box naming convention (added 2026-08-08)

> **Important for image maintainers:** the AP SSID and
> The default hostname is `g90digi`. Operators should override it (and the matching AP SSID, ZT identity, etc.) via `bootstrap.sh` or pre-first-boot edits.
> (AP: `g90digi`, hostname: `g90digi`, mDNS:
> `g90digi.local`). These are the **defaults** baked into
> the source files in this folder. When you flash this
> image onto a different box, you should:

1. **Change the hostname** to match the box's identity:
   ```bash
   sudo hostnamectl set-hostname <new-hostname>
   sudo sed -i 's/^127.0.1.1.*/127.0.1.1\t<new-hostname>/' /etc/hosts
   ```
2. **Change the AP SSID** in two places:
   - `/etc/hostapd/hostapd.conf` (`ssid=` line)
   - `/etc/reticulumhf/config.env` (`RETICULUMHF_AP_SSID`)
3. **Change the user-facing wifi instructions** in
   `/home/pi/node-portal/templates/index.html` (search
   for the SSID string)
4. **Restart the services** that depend on the SSID:
   ```bash
   sudo systemctl restart hostapd
   sudo systemctl restart node-portal
   ```

> **Customizing the deploy defaults:** the hostname, AP SSID, and ZeroTier network ID baked into this image are **defaults**. Operators should override them via the `bootstrap.sh` script (or by editing the overlay files before first boot). Group-specific values are documented in the `smeshT/g90digi` repo.
## Pi 4 historical

The previous-generation Pi 4 overlay (BCM2711, 32-bit-friendly,
`g90digi` SSID) is preserved at `g90-image/pi4/` for reference
and as the lineage of how this project got here. **Do not edit
it for new work** — this directory (`g90-image/`) is the canonical
recipe for both Pi 4 and Pi 5 deployments via the dual-arch
capability verified on 2026-08-09 (one image, both targets).

## Relationship to the live deployed boxes

The two fleet boxes that consume this overlay are:

- **`g90f1r2.local`** (ZT <your-ZT-IP>) — shipping, on ECG_Guest
  wifi, last captured image in `/REMOTE/pi_images/pi5-g90digi-8-9-26.img.xz`


This overlay is the **canonical recipe** for both. Captured
flashable images live in `/REMOTE/pi_images/` (NOT in this repo —
the .img.xz files are too big for git, and they capture state
snapshots rather than recipe state).

## Dual-arch policy (2026-08-09)

Per `memory/g90-project.md` → "Image policy and dual-arch
compatibility," one captured image deploys to both Pi 4 (64-bit
mode) and Pi 5. The recipe in this overlay is the same for both
architectures; the kernel/DTB handling at image-build time is what
makes them dual-arch (kernel8.img + kernel_2712.img side by side,
arm_64bit=1 in config.txt).

## Group-specific secrets (SSID, password, callsign, freqs)

**None of those go in this repo.** They live in `smeshT/g90digi/`
(a separate, group-only repo) and are layered onto a captured image
at deploy time, not at build time. This repo is shareable; the
fleet-config is not.
