# g90 Project (g90digi image + shared launcher)

_Started 2026-06-25, last major work 2026-07-07._

This document is the **canonical reference** for the g90
project: the g90digi image (the image we flash to the g90
Pi), the shared launcher (Flask app on port 8090), the
wifi page (node-portal on port 80), and the workflow for
re-deploying to a fresh image. For the day-by-day
session log see `memory/2026-06-25.md`,
`memory/2026-06-27.md`, and `memory/2026-07-07.md`. For
the current state of the live g90 box (when it's up) see
the daily log of the most recent session.

## Hardware

**g90digi** is a Raspberry Pi image that wraps the
G90/QYT KT-8900D mobile radio + a USB sound card into a
self-contained digital-mode box. Originally derived from
the sbitx Reticulum project (which wraps a SoftRock-style
HF rig), g90digi is its UHF/VHF sibling for the QYT
mobile.

**Current deployed units (2026-07-07):**
- `g90f1r2` — shipping unit, just renamed. mDNS
  `g90f1r2.local`, ZeroTier IP <shipping-box-ZT-IP>.
- `g90digi` — offline unit, original hostname.
  mDNS `g90digi.local` (no longer collides with the shipping g90), ZeroTier IP unknown.

**Historically configured ZeroTier IPs** (probably
dead; use mDNS or LAN IP first): <shipping-box-ZT-IP> (shipping), <other-ZT-IP> (was a different config
in earlier sessions; current address is whatever
ZeroTier assigns now). sbitx's <ZT-IP> was
also dead for a while — see `memory/MEMORY.md`.

**The g90 box is currently OFFLINE** as of 2026-07-07
even though we re-flashed and re-deployed on the LAN
mDNS IP. Reason unknown; the user is investigating. The
workspace copy at
`/home/pi/.openclaw/workspace/g90-shared-launcher/`
holds the full source of truth for re-deploy.

## Image

The g90digi image is bookworm aarch64 with:

- ARM aarch64, kernel 6.6.51+rpt-rpt-v8
- patmenu2 v2.12.1 at `/home/pi/patmenu2/` (do NOT
  touch per user rule)
- flrig 1.4.7, hamlib 4.5.5 (apt)
- ARM HF (32-bit) compat layer (dpkg --add-architecture
  armhf + ~166 armhf libs) for piardopc/piARDOP_GUI
- node-portal at `/home/pi/node-portal/` (Flask, port 80)
- reticulumhf-portal at
  `/opt/reticulumhf/setup-portal/` (Flask, separate
  config wizard)
- reticulumhf-rnsd (enabled at boot),
  reticulum-meshchat, freedvtnc2 (DISABLED at boot
  per user policy — see "Services" below)
- node-portal already brings up Xvfb :1, x11vnc, and
  websockify on :6080 — the shared launcher reuses
  this desktop (does not start its own)
- lxterminal: installed during this session
- pat 0.13.1-1+b4 (apt: `pat`, binary at
  `/usr/bin/pat-winlink`, symlinks at
  `/usr/local/bin/pat` and `/home/pi/.local/bin/pat`)
- piardopc 2.0.3.2 (32-bit ARM, John Wiseman's binary)
- piARDOP_GUI (32-bit ARM, same source)
- direwolf 1.8.2 (built from source, aarch64 native)
- yad (apt, needed by patmenu2 yad menu)

**Key fact about the image:** `Defaults use_pty` in
`/etc/sudoers` blocks normal sudo (the tty isn't
attached when systemd's Popen runs a child). The
workaround is the askpass helper:

- `/home/pi/.local/bin/askpass-g90.sh` —
  `#!/bin/bash
echo "<password-from-secret-store>"` (the g90 box's user
  password)
- Use: `SUDO_ASKPASS=/home/pi/.local/bin/askpass-g90.sh
  sudo -A <cmd>`
- For non-interactive: `sudo -n <cmd>` works because
  `/etc/sudoers.d/010_pi-nopasswd` has
  `pi ALL=(ALL) NOPASSWD: ***`

The askpass file is in the workspace snapshot at
`g90-shared-launcher/g90-image/config/askpass-g90.sh`
(plaintext password is OK for this local-only Pi, per
the user's 2026-07-07 standing rule).

## Image policy and dual-arch compatibility (2026-08-09)

**Key finding (2026-08-09):** The g90digi image is **dual-arch
(Pi 4 + Pi 5, 64-bit only)**. One captured image can deploy
to either architecture. We don't need separate per-arch images.

### What's in the boot partition

Both captured images
(`g90digi-2026-08-08-post-pi5-firstboot.img.gz` and
`pi5-g90digi-8-9-26.img.xz`) ship with:

- `kernel_2712.img` — `6.6.51+rpt-rpi-2712` (Pi 5 only)
- `kernel8.img` — `6.6.51+rpt-rpi-v8` (**universal aarch64**,
  works on Pi 4 AND Pi 5)
- `arm_64bit=1` in `config.txt` — forces 64-bit boot
- Pi 4 DTBs (`bcm2711-rpi-4-b.dtb`, `bcm2711-rpi-cm4.dtb`,
  etc.) — for Pi 4 boot
- Pi 5 DTBs (`bcm2712-rpi-5-b.dtb`, `bcm2712-rpi-cm5-*.dtb`)
- Pi 4 firmware (`start4*.elf`, `fixup4*.dat`)
- Pi 5 firmware (`start*.elf`, `fixup*.dat`)

### What's in the rootfs

`/lib/modules/` contains **both**:

- `6.6.51+rpt-rpi-2712/` (Pi 5 specific — for `kernel_2712.img`)
- `6.6.51+rpt-rpi-v8/` (universal aarch64 — for `kernel8.img`,
  used by Pi 4 boot)

### Pi 4 boot path

1. Bootloader sees `arm_64bit=1` → loads `kernel8.img`
2. `kernel8.img` is `6.6.51+rpt-rpi-v8` (universal aarch64)
3. Auto-detects Pi 4 SoC → loads `bcm2711-rpi-4-b.dtb`
4. Kernel mounts rootfs, loads modules from
   `/lib/modules/6.6.51+rpt-rpi-v8/`
5. Pi 4 boots successfully in 64-bit mode

### Pi 5 boot path

1. Bootloader sees `arm_64bit=1` → loads `kernel8.img`
   (preferred over `kernel_2712.img`)
2. `kernel8.img` is `6.6.51+rpt-rpi-v8` (universal)
3. Auto-detects Pi 5 SoC → loads `bcm2712-rpi-5-b.dtb`
4. Kernel mounts rootfs, loads modules from
   `/lib/modules/6.6.51+rpt-rpi-v8/`
5. Pi 5 boots successfully in 64-bit mode

**Note:** the Pi 5 *can* also boot `kernel_2712.img` (Pi 5
specific) which loads modules from `6.6.51+rpt-rpi-2712/`,
but the bootloader prefers `kernel8.img` when
`arm_64bit=1` is set.

### Caveats when booting a Pi 4

- Runs 64-bit only (not 32-bit). Fine for g90digi (already
  aarch64).
- ZT identity, SSH host keys, hostname are baked in from
  the source Pi. For a **fresh** Pi 4 box (not g90digi),
  first-boot regen needed:
  ```bash
  sudo rm /etc/ssh/ssh_host_*
  sudo ssh-keygen -A
  sudo systemctl restart ssh
  # For ZT identity (if you want a new node):
  sudo systemctl stop zerotier-one
  sudo rm /var/lib/zerotier-one/identity.*
  sudo systemctl start zerotier-one
  # Then re-join the network:
  sudo zerotier-cli join <ZT-network-id>
  ```
- For a different hostname: edit `/etc/hostname` and
  `/etc/hosts` before first boot (or `hostnamectl set-hostname`
  after).

### Image policy (revised 2026-08-09)

Before this finding: "we need separate Pi 4 and Pi 5 images."

After this finding: **one image, two targets.** The
dual-arch image (Pi 4 + Pi 5 in 64-bit mode) is sufficient
for both fleet boxes.

**Concretely:**

- **One canonical image** at `/REMOTE/pi_images/`,
  named `g90digi-<date>-<label>.img.xz`
- **Source recipe in git**: `g90-image-Pi5.git` (Pi 5
  overlay) + ReticulumHF base + g90-launcher.git
  (Flask + systemd). Both Pi 4 and Pi 5 deployments
  pull from the same recipe.
- **Rebuild on demand** when needed (~30 min: dd +
  pishrink + xz -T0 -6). Don't preemptively rebuild.
- **Pi 4 historical** stays in `g90-launcher.git/g90-image/`.
  We don't maintain a separate Pi 4 fork unless active
  Pi 4 work needs it.

### Image backup policy (`/REMOTE/pi_images/`)

Mounted from `/dev/sda1` → `/media/pi/REMOTE/`. Two tiers:

- **Latest-working** — `g90digi-<YYYY-MM-DD>-<label>.img.xz`.
  The one you'd flash today and have a working box.
- **Dev BUs** — `-WIP-<state>` or `-unknown-config` in
  label. Same dir. Opportunistic snapshots during dev;
  never confused with latest-working.
- **Sidecar `.manifest`** per backup: hostname, source
  commit, date, label, MD5, notes.
- **USB handoff pattern** for getting large images onto
  this Pi without ssh'ing to the laptop: dd on laptop →
  plug USB drive into nomadpi → cp locally → MD5-verify.

### Image shrink pipeline (pishrink + xz)

The recipe for producing a small downloadable image:

```bash
# 1. Capture (laptop dd's the live USB drive):
dd if=/dev/sda of=~/work/<radio>-<date>.img bs=4M conv=fsync status=progress
# 2. Copy to dev Pi:
scp ~/work/<radio>-<date>.img.gz pi@nomadpi:/media/pi/REMOTE/pi_images/
# 3. Shrink + compress on dev Pi:
sudo pishrink -Z /media/pi/REMOTE/pi_images/<radio>-<date>.img
# 4. Verify:
xz -t /media/pi/REMOTE/pi_images/<radio>-<date>.img.xz
md5sum /media/pi/REMOTE/pi_images/<radio>-<date>.img.xz
```

**pishrink does:**
- `e2fsck -f` (fix live-dd inconsistencies)
- `resize2fs -M` (shrink rootfs to minimum)
- `parted` resize + truncate (image = used space only)
- `xz -9` (compress; `xz -T0 -6` for ~3x faster with ~10%
  larger output)

**Typical sizes:**
- 28 GB raw disk → 5-6 GB after pishrink → 1-2 GB after xz

### Lessons learned on image building (2026-08-09)

- **`zerofree` on a mounted rw filesystem is required before
  dd'ing the source.** pishrink's resize2fs -M still works
  on a live-captured image (e2fsck -f repairs journal),
  but the image compresses better if the source was
  zero-filled first. We skipped zerofree in our last
  capture (it complained about mounted rw); pishrink
  handled it but the .img.xz is ~25% larger than it
  would be otherwise.
- **`xz -9` (single-threaded) takes ~2-3 hours for 6 GB
  on a 4-core Pi.** Use `xz -T0 -6` (parallel, level 6)
  instead — ~25 min for 6 GB, output is ~5% larger.
- **Pishrink without `-a` (parallel mode) is single-threaded.**
  On a 4-core box, pass `-a` for parallel gzip/xz, or
  set `PISHRINK_XZ="-T0 -6"` env var.
- **Detach long-running exec calls.** A 30-min `dd` got
  killed by an OpenClaw tool policy change. Always wrap
  long-running commands with `setsid + nohup + &` and
  detach from the exec shell.
- **The Pi 5's USB-C power negotiation can fail with
  some USB drives during sustained writes.** Two
  different USB drives failing Pi Imager's "error
  reading from storage" in two days = symptom, not
  cause. Workarounds: (a) write via `dd` from the
  laptop, (b) use a powered USB hub, (c) prefer USB
  2.0 black ports over USB 3.0 blue ports.

## The shared launcher (port 8090)

A Flask app we wrote from scratch this session, modeled
on the sbitx my_launcher. Source of truth:
`/home/pi/.openclaw/workspace/g90-shared-launcher/`
on the nomadpi. Deployed to
`/home/pi/shared_launcher/` on the g90.

**Why a separate launcher instead of just node-portal?**
- The sbitx box has its own my_launcher (port 8090);
  the g90 is its sibling — same Flask-app pattern, same
  port, separate code path. The two don't share state.
- node-portal is the g90 image's official
  "wifi/apps/per-app start" interface, but it's
  service-oriented (one button per app, with hardcoded
  systemd unit names). The shared launcher is
  workflow-oriented (a clean grid of digimode/audio/
  Reticulum/power groups).

**Service state on the g90 box (2026-07-07):**

| Service | State | Port | Notes |
|---|---|---|---|
| g90-shared-launcher.service | enabled, active | 8090 | this launcher |
| pat-http.service | DISABLED at boot | 5000 | user opted-out of auto-start |
| node-portal.service | active | 80 | wifi + apps pages |
| reticulumhf-portal.service | active | — | ReticulumHF setup |
| reticulumhf-wlan.service | enabled | — | WiFi AP |
| reticulumhf-firstboot.service | enabled | — | g90 image setup |
| reticulumhf-rnsd.service | DISABLED at boot | — | only via Reticulum Stack |
| reticulum-meshchat.service | DISABLED at boot | — | only via Reticulum Stack |
| freedvtnc2.service | DISABLED at boot | — | only via Reticulum Stack |
| rigctld.service | active | 4532 | radio control |
| x11vnc | active | 5900 | VNC |
| websockify | active | 6080 | noVNC |

**Launcher rows (top to bottom of the panel):**

1. Open VNC Tab (link to noVNC :6080)
2. (hr)
3. **Digimode + audio:** FLrig, JS8Call, FLDigi, WSJT-X
   (each row: help-link name + Start + Stop)
4. Pat Menu (Pat UI link, Start, Stop)
5. Pavucontrol
6. Reset Audio Devices
7. (hr)
8. **Reticulum:** Reticulum Stack, MeshChat, FreeDVtnc2
9. (hr)
10. **Power + WiFi button bar (no name):** Wifi, Old Apps,
    Reboot, Shutdown

**Status pills (top of page, flex-wrap):**

Row 1: FLrig / JS8Call / FLDigi / WSJT-X / Pavucontrol
Row 2: Pat Menu / Pat
Row 3: RNS / MeshChat / FreeDV TNC

**Status pill for "FreeDV TNC":** wired to
`service_active("freedvtnc2.service")
or is_running("lxterminal --title=freedvtnc2")` so it's
green whether the daemon is up OR the lxterminal CLI is
running. One pill, two meanings — the user explicitly
chose this so they don't have to track which freedvtnc2
mode is in use.

**Status pill for "Pat":** red by default. The user
explicitly wanted pat-http off by default to prevent
accidental outbound from queued messages. The Pat Menu
row's Start button now starts pat-http (with
reset-failed first); the Pat UI link just opens the
browser tab.

**Routes the launcher exposes (all on port 8090):**

- `GET /` — index (status pills + rows)
- `POST /start-js8call`, `/stop-js8call`, etc. for each
  digimode
- `POST /start-patmenu`, `/stop-patmenu` — control
  pat-http.service (and incidentally the yad menu via
  start_patmenu.sh / stop_patmenu.sh)
- `POST /start-pavucontrol`, `/stop-pavucontrol`
- `POST /reset-audio` — stops meshchat/rnsd/freedvtnc2,
  restarts novnc-session
- `POST /start-reticulum`, `/stop-reticulum`,
  `/restart-reticulum` — the Reticulum stack
- `POST /start-freedv-tui`, `/stop-freedv-tui` — the
  FreeDV lxterminal in noVNC
- `POST /reboot-pi`, `/shutdown-pi` — system control
- `POST /start-pat-http`, `/stop-pat-http` — API-only
  routes (no UI buttons; used by the yad's start-modem
  backdoor)

**Help-link styling** (this session): the four digimode
row names (FLrig, JS8Call, FLDigi, WSJT-X) are
`<a class="help-link">` elements that link to
`/help/<app>` on the node-portal. Visually they look
like the plain text `<div class="name">` rows (no
border, same font, same color) — the only signal
they're clickable is the cursor pointer and the
underline on hover. They have a `title="<App> Help
Page"` attribute for native browser tooltips.

**The `row-buttons` span wrapper** (this session): on
phone (the user's primary client), the `.row` becomes
`flex-direction: column` so each child takes its own
line. Without a wrapper, Start and Stop would stack
vertically with full-width buttons. The
`.row-buttons` span wraps the Start+Stop pair as a
horizontal flex container, so they sit side-by-side on
the same row in the column.

## The wifi page (node-portal, port 80)

Edits to `/home/pi/node-portal/templates/index.html`
(this session):

- Renamed the "Open Apps Launcher" button behavior to
  point at the **shared launcher** (POST to
  `/open-shared-launcher`, 302 to :8090)
- Added a new "Old Apps Page" button (onclick →
  `/apps`, the original node-portal apps page)
- Removed the descriptive `<span>` text under each
  button (cleaner)
- Removed the broken `<script>togglePassword()</script>`
  block (the password field stays type="password" — no
  Show Password button works; user accepted this)

Snapshotted to:
`/home/pi/.openclaw/workspace/g90-shared-launcher/g90-image/node-portal-templates/`

**To reapply:** copy `index.html` over
`/home/pi/node-portal/templates/index.html` on the g90,
then `sudo systemctl restart node-portal.service`.

## The Reticulum / FreeDV stack (port 8000, 9993, 4242)

- `rnsd` (reticulumhf-rnsd) — Reticulum network daemon.
  Bound on 9993 (Reticulum default) and 4242 (rnode).
  ENABLED at boot.
- `meshchat` (reticulum-meshchat) — LXMF-based chat.
  Bound on 8000 (web UI). DISABLED at boot.
- `freedvtnc2` (freedvtnc2.service) — FreeDV TNC,
  KISS TNC for the mesh. Bound on 8001 (KISS),
  8002 (cmd). DISABLED at boot.

**The launcher's Reticulum Stack: Start button** does:

```python
systemctl("reset-failed", "reticulumhf-rnsd.service",
                       "reticulum-meshchat.service",
                       "freedvtnc2.service")
systemctl("start", "reticulumhf-rnsd.service",
                    "reticulum-meshchat.service",
                    "freedvtnc2.service")
```

The reset-failed before start is important: freedvtnc2
will land in systemd's rate-limited "failed" state
after 5 crashes in 60s (no G90 audio) and refuse to
restart on subsequent clicks. The reset clears that.

**The FreeDV TUI (lxterminal) on phone (noVNC):**

`/home/pi/shared_launcher/scripts/freedv_tui.sh`
sources `/etc/reticulumhf/config.env`, strips
`--no-cli` from the FREEDVTNC2_CMD, and runs the
resulting command in an lxterminal on Xvfb :1. The
script has a pre-flight audio check (if `arecord -l`
doesn't show the configured input device, it opens the
terminal with a "plug in the G90" message instead of
trying to run freedvtnc2). Idempotency check uses
the lxterminal's `--title=freedvtnc2` (not a loose
`pgrep -f`, which self-matches the ssh wrapper).

## Bug history (this session)

These are the bugs we hit, in order. Future-me reading
the live g90 should know about them.

1. **start_patmenu.sh idempotency** (fixed 19:50):
   the for-loop version, not the pipe-and-while
   version. The pipe version always returns 0 (empty
   pgrep -> empty while -> pipe close status 0) and
   silently no-ops.
2. **stop_patmenu.sh missing** (fixed 19:50): the
   file wasn't in the g90's launcher dir at all. Now
   uses `stop_proc "patmenu2/pmlogo.png"` (matches
   every yad dialog from patmenu2, not just the main
   menu which has title="Pat Menu" but the callsign
   check which has title=N0CALL).
3. **"Pat Menu" status pill pgrep self-match** (fixed
   19:50): the original `is_running("Pat Menu")` had
   two bugs — (a) didn't match the yad when title was
   N0CALL, (b) self-matched the ssh wrapper bash whose
   argv contained "Pat Menu". Changed to
   `is_running("patmenu2/pmlogo.png")`.
4. **meshchat ratchet file corrupt** (fixed 20:03):
   `/home/pi/reticulum-meshchat/storage/identities/c5471dd5bdf09709db2232e729ab2ded/lxmf_router/lxmf/ratchets/f77bdc818a6fb889e9f5666902576e2c.ratchets`
   was 0 bytes (since 2026-05-24). meshchat was in a
   1.6s crash loop. Fixed by deleting the empty file
   (meshchat regenerates it). **TODO: add
   `find ... -size 0 -delete` to the image's
   firstboot.**
5. **freedvtnc2.service rate-limited** (fixed 20:45):
   after 5 crash retries the service was in systemd's
   rate-limited "failed" state. The launcher's Start
   button now calls `systemctl reset-failed` first.
6. **Workspace/g90 drift** (recurring): the workspace
   copy of the launcher got out of sync with the g90
   several times this session (the "fix" I thought I
   pushed wasn't actually pushed, or the push
   succeeded but a later push overwrote it). **Rule
   for future-me:** when debugging "the g90 file is
   wrong," first verify the g90 file content via ssh,
   not the workspace. Workspace is source of truth
   for re-deploy, not the g90's runtime state.

## Known footguns (NOT bugs, just things to know)

- **No radio, no audio** — the g90 box has no G90
  plugged in (audio device 1 doesn't exist). freedvtnc2
  will fail to start. This is fine, it's the expected
  "no radio" state. The user has not yet decided what
  to do when they DO plug in the G90 (presumably just
  click Reticulum Stack: Start).
- **patmenu2's "Start Modem" button doesn't work**
  because lxterminal wasn't installed until this
  session, and the yad's modem flow still hasn't been
  end-to-end tested. The dead `curl -X POST /start-
  pat-http` line in start-pat-ardop is benign
  because the script never gets that far. **TODO: when
  the yad is fixed, decide whether to keep the curl
  line (yad auto-starts pat-http) or remove it
  (preserve "pat-http off" guarantee).**
- **patmenu2 source NOT touched** per user's standing
  rule, EXCEPT for the start-pat-ardop edit (which
  was approved explicitly).
- **flrig is treated as an accessory** — never killed
  by the launcher's stop-flrig button. The user runs
  flrig manually from the noVNC desktop.
- **patmenu2 config NOT touched** — N0CALL stub stays
  until the user edits MYCALLSIGN via the yad menu
  (Settings -> Current Config Settings).

## Deploy pattern (workspace → g90)

```bash
# On the nomadpi:
cd /home/pi/.openclaw/workspace
tar czf - g90-shared-launcher/ \
    | /tmp/ssh-g90-tar.sh \
      "rm -rf /home/pi/shared_launcher/g90-shared-launcher && \
       tar xzf - -C /home/pi/shared_launcher/ --strip-components=1 && \
       sudo -A systemctl restart g90-shared-launcher.service"
```

**Critical gotcha:** use `--strip-components=1` or files
land in a nested `g90-shared-launcher/` subdir and the
live files don't get updated. We hit this earlier in the
session; the rm -rf + strip pattern is the fix.

**For the wifi page:**
```bash
# Shipping g90:
scp g90-shared-launcher/g90-image/node-portal-templates/index.html \
    pi@g90f1r2.local:/home/pi/node-portal/templates/index.html
/tmp/ssh-g90-now.sh "sudo -A systemctl restart node-portal.service"

# Offline g90 (when online):
scp g90-shared-launcher/g90-image/node-portal-templates/index.html \
    pi@g90digi.local:/home/pi/node-portal/templates/index.html
# (use whichever ssh wrapper / host is current for the offline g90)
```

**Note for the offline g90:** the workspace snapshot
at `g90-image/config/{reticulumhf-config.env,hostapd.conf}`
has the **shipping g90's** AP values (`g90f1r2`,
password `CHANGE_ME`). If the user wants the offline
g90 to keep its original `g90digi` AP SSID, skip
those two files when pushing. If the user wants
both g90s to share the same AP, push them as-is.
See the addendum below for the full trade-off.

## File inventory

### Source of truth (workspace)
- `/home/pi/.openclaw/workspace/g90-shared-launcher/`
  - `app.py` — Flask routes
  - `templates/index.html` — launcher template
  - `scripts/*.sh` — start/stop scripts (12 total)
  - `g90-shared-launcher.service`, `pat-http.service`
  - `start_my_launcher.sh`
  - `g90-image/` — snapshot of the g90 image state
    (node-portal templates, configs, systemd units,
    patmenu2 edits) — see `g90-image/README.md`

### Live on the g90 box
- `/home/pi/shared_launcher/` — Flask app (deployed)
- `/etc/systemd/system/g90-shared-launcher.service`
- `/etc/systemd/system/pat-http.service`
- `/home/pi/.config/pat/config.json` (N0CALL stub)
- `/home/pi/.local/bin/askpass-g90.sh`
- `/etc/reticulumhf/config.env`
- `/usr/local/bin/start-novnc-session` (1280x800)
- `/home/pi/node-portal/templates/index.html`
  (the wifi page with the two apps buttons)

## Lessons (this session)

1. **When you can't push, the g90 file is the live
   truth.** Verify via ssh before debugging.
2. **pgrep -f "<substring>" self-matches** when the
   substring is in the calling command's argv. Use
   patterns that are path-based and not in any
   command-line interface text (e.g. `pmlogo.png` is
   uniquely in patmenu2's yad).
3. **`is_running("Pat Menu")` is wrong** because the
   yad title is the user's callsign, not "Pat Menu."
   Use a pattern that's in the cmdline, not the title.
4. **systemd rate-limits failed services** with
   `StartLimitBurst=5 / interval=60s`. After 5 fast
   failures, `systemctl start` is a no-op until
   `systemctl reset-failed`.
5. **Empty ratchet files break meshchat** silently.
   `find ... -size 0 -delete` should be in the g90
   image's firstboot.
6. **`/shutdown` and `/reboot` routes are real** — they
   actually power-cycle the box. Test by reading the
   code, not by POSTing to them.
7. **A `reset-failed` before every `start`** is a good
   default for systemd services that can crash (i.e.
   almost all of them).
8. **The launcher's UI should mirror the user's mental
   model**, not the implementation. "Pat Menu" in the
   user's head = "the pat experience," not "a yad
   process." When in doubt, ask the user what the row
   *means* to them.
9. **Native HTML `title` attribute is the right
   tooltip.** Accessible, no JS, consistent across
   browsers.
10. **Phone layout in flex containers: when the
    direction changes to column, sibling elements
    that should stay paired need a wrapper.** The
    `.row-buttons` span is the wrapper for
    Start+Stop.
11. **The "Open" button on a noVNC link row is
    redundant** with the standalone Open VNC Tab at
    the top. Drop it.
12. **Tying pill state to the wrong thing**
    (e.g. showing "Running" when the ssh wrapper
    self-matches) is worse than no pill at all. The
    user trusts the pill to mean "this app is up." A
    misleading pill is a debugging trap.

## Addendum (2026-07-07, pre-ship)

**Two g90s as of this date:**
- **Shipping g90** (`g90f1r2`) — hostname `g90f1r2`,
  AP SSID `g90f1r2`, AP password `CHANGE_ME`. Same
  password/askpass as before (user wants both g90s to
  share credentials so user can always SSH in
  remotely).
- **Offline g90** (`g90digi`) — keeps the original
  hostname and AP settings. mDNS collision resolved
  by the rename.

**Pre-ship steps taken (live on g90f1r2):**
- `sudo -A hostnamectl set-hostname g90f1r2` +
  `/etc/hosts` edit + `systemctl restart avahi`
- `/etc/hostapd/hostapd.conf` rewritten with the new
  SSID (channel 7, wpa_passphrase kept the same)
- `/etc/reticulumhf/config.env` updated to match
  (also added `RETICULUMHF_AP_CHANNEL=7` which was
  missing)
- `systemctl restart hostapd.service`
- The ssh wrappers on the nomadpi updated:
  `/tmp/ssh-g90-now.sh` and `/tmp/ssh-g90-tar.sh`
  now point at `pi@g90f1r2.local`

**Known footgun added this session:**
`/opt/reticulumhf/scripts/wifi-ap.sh` is buggy on the
g90 image — it tries to restart `dhcpcd.service` which
doesn't exist (g90 image uses NetworkManager instead).
The script fails at that step. Workaround: edit
`/etc/hostapd/hostapd.conf` directly, then
`sudo -A systemctl restart hostapd.service`. Don't run
the script. Same workaround applies to the offline
g90 if anyone ever runs it there.

**For the offline g90 (when it's online):** the
workspace snapshot at
`g90-image/config/{reticulumhf-config.env,hostapd.conf}`
has the **shipping g90's** values (g90f1r2). The
user can either:
- Push the snapshot as-is (offline g90 gets the new
  SSID too — both g90s would broadcast `g90f1r2`
  which is confusing)
- Update the snapshot first to give the offline g90
  its own SSID (e.g. `g90digi`) before pushing
- Skip the hostapd.conf / config.env updates
  entirely (offline g90 keeps the old SSID
  `g90digi` and the offline g90's mDNS name remains
  `g90digi.local`)

The launcher UI (the workspace at
`g90-shared-launcher/`) and the wifi page
(node-portal) updates should be pushed regardless.

