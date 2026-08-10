# g90 image state (snapshotted 2026-07-07, updated 2026-07-08)

This folder is a **portable snapshot** of the g90 box's
"image state" — the configuration files that were edited
or installed on top of the stock g90digi image. It exists
so that, when the remote g90 Pi comes back online, the
same edits can be reapplied to a fresh flash without
having to re-derive them.

The **shared launcher** (Flask app, port **8090** — the wifi clients' home page) lives in
the **parent** of this folder. It is a git clone of
`/home/pi/repos/g90-launcher.git` on the nomadpi, NOT a
direct copy. The full architecture is documented in
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
`/home/pi/repos/g90-launcher.git` is the central pull
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

# 1. Generate an SSH key (for git pull from the nomadpi)
ssh-keygen -t ed25519 -N "" -f /home/pi/.ssh/id_ed25519
cat /home/pi/.ssh/id_ed25519.pub  # copy to nomadpi's authorized_keys

# 2. Clone the launcher
sudo -A -u pi git clone pi@nomadpi.local:/home/pi/repos/g90-launcher.git /home/pi/shared_launcher
sudo chown -R pi:pi /home/pi/shared_launcher

# 3. Install the systemd unit
sudo cp /home/pi/shared_launcher/g90-shared-launcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now g90-shared-launcher.service

# 4. (If migrating from an old direct-copy install) move the
#    old /home/pi/shared_launcher out of the way first
sudo mv /home/pi/shared_launcher /home/pi/shared_launcher.old

# 5. Then proceed with steps 2-3

# 6. Copy the g90-image/ contents into place (only the
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
- `askpass-g90.sh` — g90 user password (6292), in plaintext
  (this is a local-only Pi, the trade-off is OK)

  **⚠️ 2026-07-20 — this PIN is now compromised.** The 4-digit
  password `6292` was pasted in the @Mmsp907 ⇄ @CletusTbot
  Telegram DM on 2026-07-20 and is in chat history. New g90
  boxes flashed from this image inherit the same PIN, so
  the leak multiplies with every flash. **Action for whoever
  has root on the g90 / dev Pi:** (a) `sudo passwd pi` on
  the g90 with a passphrase longer than 4 digits, (b) update
  `~/.ssh/.g90-pass` on the dev Pi to match, (c) ideally
  replace this file's contents with a fresh, per-box
  password generated on first boot. **Structural fix:** ssh
  keys. See `memory/g90-project.md` "Known footguns" →
  "g90 ssh password leaked via Telegram."
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

The wrappers `/tmp/ssh-g90digi-now.sh` and
`/tmp/ssh-g90digi-tar.sh` (still pointed at the
shipping g90) need to be re-pointed at the offline
g90's IP. Then:
1. Update the IP in those wrappers
2. SSH in, follow the "First-time setup" steps above
3. The Update button on the launcher's bottom row will
   pull the latest code on demand.

## Per-box naming convention (added 2026-08-08)

> **Important for image maintainers:** the AP SSID and
> hostname baked into this image default to **`g90digi`**
> (AP: `g90digi-AP`, hostname: `g90digi`, mDNS:
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

> **Note on g90digi vs g90f1r2:** historically this image
> defaulted to `g90f1r2-AP` because the source image was
> cloned from the g90f1r2 box. As of 2026-08-08, the
> default has been changed to `g90digi-AP` to match the
> currently-deployed box. **If you ever publish this
> image publicly**, double-check that the SSID matches
> your intended default — operators may not expect to
> have to rename the AP on first boot.

> **The two units (`g90digi` and `g90f1r2`) are
> separate physical radios with separate image
> deployments.** They share the same source image (this
> folder) but each instance has its own hostname, AP
> SSID, ZeroTier identity, and (currently)
> ZeroTier-assigned IP. Don't assume they're the same
> box just because the image is the same.

## Pi 4 historical

The previous-generation Pi 4 overlay (BCM2711, 32-bit-friendly,
`g90f1r2-AP` SSID) is preserved at `g90-image/pi4/` for reference
and as the lineage of how this project got here. **Do not edit
it for new work** — this directory (`g90-image/`) is the canonical
recipe for both Pi 4 and Pi 5 deployments via the dual-arch
capability verified on 2026-08-09 (one image, both targets).

## Relationship to the live deployed boxes

The two fleet boxes that consume this overlay are:

- **`g90f1r2.local`** (ZT 10.59.42.236) — shipping, on ECG_Guest
  wifi, last captured image in `/REMOTE/pi_images/pi5-g90digi-8-9-26.img.xz`
- **`g90digi.local`** (ZT 10.59.42.237) — Pi 5 2GB replacement, the
  reference "latest stable" box

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

**None of those go in this repo.** They live in `g90-fleet-config/`
(a separate, group-only repo) and are layered onto a captured image
at deploy time, not at build time. This repo is shareable; the
fleet-config is not.
