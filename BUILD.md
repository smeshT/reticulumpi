# Building a g90 box from source

### Outdated info use **[Build from Script](README.md)**

This is the **end-to-end recipe** for building a g90 box
(Raspberry Pi 4 or Pi 5 running the g90digi image, configured
for a Xiegu G90 / QYT KT-8900D HF radio) starting from a
stock ReticulumHF base image.

> **Don't want to build it yourself?** A pre-built image is
> published as a GitHub Release on the
> [smeshT/reticulumpi](https://github.com/smeshT/reticulumpi/releases)
> repo. **However:** as of v0.6.18, the published pre-built
> image is still the v0.5 image from 2026-08-09. Future
> pre-built images (v0.6.x) will land once the clean-build
> recipe below is end-to-end verified on a fresh Pi.
> Until then, follow this recipe to build from source.

> **v0.6.18 hardening:** every install/cp/enable step in this
> recipe is followed by a `## verify` block. Run the verify
> command immediately after each step. If verification
> fails, **stop and fix that step before continuing.** A
> failure caught 30 seconds after it happened takes 30
> seconds to fix; a failure caught 5 steps later takes
> 5 minutes to backtrack to.

## What you need

- **Raspberry Pi 4 (2GB+) or Pi 5 (2GB+)** — 64-bit mode
  required. The same image boots either architecture.
- **USB drive or SD card, 16 GB minimum, 32 GB recommended**
  (the captured image is ~6 GB pishrunk, ~28 GB raw; 32 GB
  gives you headroom for logs and mesh storage).
- **Xiegu G90 or QYT KT-8900D** radio (other radios may work
  but are untested)
- **Radio Interface** DigiRig or Xiegu CE/DE-19
- **FTDI USB-serial cable** (for CAT control of the G90)
- **A laptop or desktop with Raspberry Pi Imager installed**

## Overview

The build pipeline is **two layers**:

1. **Base layer** — stock ReticulumHF image. Provides the
   Pi's AP + captive portal, rnsd, freedvtnc2, noVNC, etc.
   Get it from the Light Fighter Manifesto [resources
   page](https://lightfightermanifesto.org/resources/) or the
   [LFManifesto/ReticulumHF releases on
   GitHub](https://github.com/LFManifesto/ReticulumHF/releases/)
   (current stable: v1.0).
2. **Overlay layer** — this repo's `g90-image/` + `g90-launcher/`
   folders. Adds the g90-specific shared launcher, patmenu2
   edits, ARDOP PTT bridge, FTDI cable setup, audio dsnoop,
   and g90-aware systemd units.

Estimated build time: **45-60 minutes on a Pi 4**, mostly
package installation and `apt update`.

## Step 1 — Flash the base image

```bash
# Download the latest ReticulumHF base image from
# https://lightfightermanifesto.org/resources/ (the Light Fighter
# resources index — ReticulumHF v1.0 stable link)
# OR from the github releases:
# https://github.com/LFManifesto/ReticulumHF/releases/

# Flash with Raspberry Pi Imager:
#   1. Open Pi Imager
#   2. Choose OS → "Use custom" → select the ZIP
#   3. Choose Storage → select your SD card or USB drive
#   4. (Recommended) click the gear icon and set:
#        - hostname: g90digi (or your preferred name)
#        - enable SSH with password auth (for first-boot setup)
#        - username: pi
#        - password: (set your own — NOT the bundled default)
#        - locale / timezone: yours
#   5. Write
```

Pi Imager handles ZIP extraction automatically — no manual
unzip needed.

## Step 2 — First boot the base

1. Plug the SD card / USB drive into the Pi.
2. Power on. The Pi boots, expands the rootfs to fill the
   drive, and reboots (~30-60 seconds).
3. After reboot, find the Pi on your network:
   - **mDNS:** `ssh pi@<hostname>.local` (or whatever hostname
     you set)
   - **LAN IP:** check your router's admin page, or use
     `nmap -sn 192.168.1.0/24` (replace with your subnet)
   - **AP:** the Pi broadcasts a `ReticulumHF` wifi network
     (default password on the printed card in the box). Connect
     to it; the Pi is at `192.168.4.1`.
4. SSH in: `ssh pi@<hostname>.local` (or LAN IP).
5. Run `sudo apt update && sudo apt upgrade -y` and reboot.
   This pulls the latest package versions. (~10-15 min on Pi 4)

## verify

```bash
# Confirm you're on a recent base
cat /etc/os-release | grep PRETTY_NAME
# expected: PRETTY_NAME="Raspbian GNU/Linux 12 (bookworm)"

uname -m
# expected: aarch64

# Confirm SSH works (you just used it, so yes)
whoami; hostname
```

## Step 3 — Add non-default apt sources

The ReticulumHF base image's default bookworm repos don't
ship `zerotier-one`. We need to add ZeroTier's official
apt source before any install. **Do this step before
Step 3a, otherwise Step 4's `apt install zerotier-one`
will fail with "E: Unable to locate package" and Step 6
will fail with "Unit file does not exist" 5 minutes later.**

```bash
# Add ZeroTier's official signing key
curl -fsSL 'https://raw.githubusercontent.com/zerotier/ZeroTierOne/main/doc/contact%40zerotier.com.gpg' \
    | sudo gpg --dearmor -o /usr/share/keyrings/zerotier-archive-keyring.gpg

# Add the ZeroTier apt source (bookworm-specific)
echo 'deb [signed-by=/usr/share/keyrings/zerotier-archive-keyring.gpg] https://download.zerotier.com/debian/bookworm bookworm main' \
    | sudo tee /etc/apt/sources.list.d/zerotier.list

sudo apt update
```

## verify

```bash
apt-cache policy zerotier-one
# expected output includes:
#   Candidate: 1.16.2
#   *** 1.16.2 ... download.zerotier.com/debian ...
# If it says "(none)" or no Candidate, the apt source wasn't added.
```

## Step 3a — Install overlay packages

> **Pre-seed dpkg answers before any apt install** so the
> build is fully non-interactive. ReticulumHF base images
> sometimes carry locally-modified config files (notably
> `/etc/initramfs-tools/initramfs.conf`) that the .deb's
> post-install would otherwise pause to ask about. Setting
> `DEBIAN_FRONTEND=noninteractive` tells dpkg to keep the
> existing local version for any modified config — same as
> pressing N at the prompt, but without blocking the build.
>
> ```bash
> export DEBIAN_FRONTEND=noninteractive
> ```
>
> Add this once before Block 1; it stays in effect for the
> rest of the shell session.

Install each block separately. **Do not paste all of them
into one terminal at once** — that's how the manual
build hit paste-mash errors.

```bash
# Block 1: core tools + apt deps
sudo apt install -y \
    git curl wget xz-utils gpg \
    python3 python3-pip python3-venv \
    flrig hamlib pat \
    fldigi js8call wsjtx \
    direwolf \
    avahi-daemon avahi-utils \
    xterm lxterminal pulseaudio pavucontrol
```

## verify

```bash
# Every binary above should resolve. Anything that says "not found" failed.
for b in git curl wget xz gpg python3 pip flrig hamlib pat fldigi js8call wsjtx direwolf avahi-daemon avahi-utils xterm lxterminal pulseaudio pavucontrol; do
    command -v "$b" >/dev/null && echo "OK: $b" || echo "MISSING: $b"
done
```

```bash
# Block 2: zerotier (now available because Step 3 added the source)
sudo apt install -y zerotier-one
# If the .deb's post-install errored, finish it:
sudo dpkg --configure -a
```

## verify

```bash
which zerotier-cli
# expected: /usr/bin/zerotier-cli

file /usr/sbin/zerotier-one
# expected: ELF 64-bit LSB executable, ARM aarch64

ls -la /lib/systemd/system/zerotier-one.service
# expected: -rw-r--r-- 1 root root ... /lib/systemd/system/zerotier-one.service
# (The upstream .deb ships the unit at /lib/systemd/system/,
#  which has lower precedence than /etc/systemd/system/ but
#  is the canonical source.)
```

```bash
# Block 3: pipx for Reticulum stack
sudo apt install -y pipx
pipx ensurepath
```

## verify

```bash
command -v pipx
# expected: /usr/bin/pipx or /usr/local/bin/pipx
pipx --version
# expected: 1.x.x
```

```bash
# Block 4: pipx venvs (the launcher's Reticulum stack)
#
# CRITICAL: the launcher's component check does `import RNS` and
# `import lxmf` from the rns venv, not from a separate lxmf venv.
# So we install lxmf INTO the rns venv via `pipx inject`, not as
# its own `pipx install lxmf`. Otherwise the component check
# reports "lxmf not installed" even though `lxmd` works.
#
# Also: rns must be at 1.4.0+ (ReticulumHF base ships 1.1.3, which
# is too old). Force-upgrade to 1.4.2 to match g90digi.

pipx install --force rns==1.4.2
pipx inject rns lxmf
```

## verify

```bash
for pkg in freedvtnc2 reticulum-meshchatx; do
    pipx list --short | grep -q "^${pkg} " && echo "OK: $pkg" || echo "MISSING: $pkg"
done

# rns and lxmf both live in the rns venv
/home/pi/.local/pipx/venvs/rns/bin/python -c "import RNS; print('RNS:', RNS.__version__)"
# expected: RNS: 1.4.2
/home/pi/.local/pipx/venvs/rns/bin/python -c "import lxmf; print('lxmf:', lxmf.__version__)"
# expected: lxmf: 1.1.x

# Confirm the binaries are on PATH
for b in freedvtnc2 lxmd reticulum-meshchatx; do
    command -v "$b" >/dev/null && echo "OK: $b" || echo "MISSING: $b"
done
```

```bash
# Block 5: modem73 (native .deb from github releases, NOT pipx)
MODEM73_VERSION="2.4.0"
MODEM73_DEB="modem73_${MODEM73_VERSION}_debian-12_arm64.deb"
wget -q "https://github.com/RFnexus/modem73/releases/download/v${MODEM73_VERSION}/${MODEM73_DEB}" \
    -O "/tmp/${MODEM73_DEB}"
sudo apt install -y "/tmp/${MODEM73_DEB}"
rm -f "/tmp/${MODEM73_DEB}"
```

> **Asset picker:** Raspberry Pi OS Bookworm arm64 (Pi 4
> 64-bit, Pi 5) → `debian-12_arm64.deb`. Pi 4 in legacy
> 32-bit mode (armhf) → `debian-12_armhf.deb`. Pi 5 with
> Ubuntu 22.04+ → `ubuntu-24.04_arm64.deb`. Browse
> https://github.com/RFnexus/modem73/releases for the full
> list.

## verify

```bash
file /usr/bin/modem73
# expected: ELF 64-bit LSB executable, ARM aarch64
/usr/bin/modem73 --help 2>&1 | head -3
# expected: usage banner with v2.4.0 build date
```

**Note on direwolf:** As of 2026-08, the apt `direwolf`
package is built for the Pi 4. For Pi 5 (aarch64 only), you
may need to build from source or skip ARDOP/direwolf if your
workflow doesn't need them.

**Note on xterm / lxterminal / pulseaudio / pavucontrol:**
ReticulumHF's base image is LXDE-free (just `Xvfb + openbox +
x11vnc`); it ships the PulseAudio user config (`~/.config/pulse/`,
`~/.config/pavucontrol.ini`) but **not** the packages. Without
`xterm`, the FreeDV TUI button does nothing (verified 2026-08-17).
Without `lxterminal`, the Modem73 Config TUI button does nothing
(verified 2026-09-08). Without `pulseaudio`, the launcher audio
rows fall back to direct ALSA, the `g90-waterfall.service`
`After=pulseaudio.service` ordering silently degrades, and
`pavucontrol` shows no sinks. Without `pavucontrol`, the Start
Pavucontrol row errors. The apt install above includes all four.
See `g90-image/IMAGE-PACKAGES.md` for the canonical list with
the "why" for each.

**Note on fldigi / js8call / wsjtx:** The launcher's audio
rows (FLrig, FLDigi, JS8Call, WSJT-X) each call into a
`start_<app>.sh` wrapper that spawns the binary directly
under `DISPLAY=:1`. Without `fldigi` the FLDigi Start button
errors with "command not found." `js8call` and `wsjtx` ARE
in Debian bookworm arm64 (`js8call 2.2.0+ds-5`,
`wsjtx 2.6.1+repack-1`), so they're safe to apt-install.

## Step 4 — Apply the overlay

```bash
# 1. Clone this repo
cd /home/pi
git clone https://github.com/smeshT/reticulumpi.git shared_launcher
cd shared_launcher

# 1a. Pin to the current launcher release tag. This is what
# gets served on port 8090; if you skip this, you're running
# whatever happened to be on main at clone time (usually a
# SHA that's newer than what's been verified on a fleet box).
git fetch
git checkout -f v0.6.18   # or whichever latest is on github
# Check https://github.com/smeshT/reticulumpi/releases for
# the current version. The version after Step 7 should be
# the same as the version pinned here.
```

## verify

```bash
cd /home/pi/shared_launcher
git describe --tags --abbrev=0
# expected: v0.6.18 (or whatever you pinned)

git rev-parse HEAD
# expected: the SHA from `git show v0.6.18 | head -1`
```

```bash
# 1b. Create the directories the overlay needs
mkdir -p /home/pi/.config/pat
# (pat's config dir only exists after pat's first run; the
# overlay cp in step 2 needs the dir to exist)
```

## verify

```bash
ls -la /home/pi/.config/pat
# expected: drwxr-xr-x 2 pi pi ... /home/pi/.config/pat
```

```bash
# 2. Copy the overlay config files into place
sudo cp g90-image/config/reticulumhf-config.env /etc/reticulumhf/config.env
sudo cp g90-image/config/hostapd.conf /etc/hostapd/hostapd.conf
sudo cp g90-image/config/pat-config.json /home/pi/.config/pat/config.json
sudo cp g90-image/config/start-novnc-session /usr/local/bin/start-novnc-session
sudo chmod +x /usr/local/bin/start-novnc-session
```

## verify

```bash
ls -la /etc/reticulumhf/config.env /etc/hostapd/hostapd.conf \
       /home/pi/.config/pat/config.json /usr/local/bin/start-novnc-session
# expected: 4 files, all present, all owned by root (config) or
# root/pi (binary)
```

```bash
# 3. Copy the systemd units from the overlay into place
sudo cp g90-image/systemd-units/g90-shared-launcher.service /etc/systemd/system/
sudo cp g90-image/systemd-units/meshchatx.service /etc/systemd/system/
sudo cp g90-image/systemd-units/lxmd.service /etc/systemd/system/
sudo cp g90-image/systemd-units/pat-http.service /etc/systemd/system/
# restart-meshchatx is a binary, not a unit; lives at /usr/local/bin/
sudo cp g90-image/systemd-units/restart-meshchatx /usr/local/bin/
sudo chmod +x /usr/local/bin/restart-meshchatx
```

## verify

```bash
ls -la /etc/systemd/system/{g90-shared-launcher,meshchatx,lxmd,pat-http}.service
ls -la /usr/local/bin/restart-meshchatx
# expected: 4 unit files + 1 binary, all present
```

```bash
# 4. Create the protected-write directories BEFORE the units start.
# Both meshchatx.service and lxmd.service run with ProtectSystem=strict
# and ReadWritePaths=, so their storage directories must exist
# before `systemctl enable --now`. The prepare-*.sh helpers are
# idempotent (mkdir -p + chown).
sudo bash g90-image/scripts/prepare-meshchatx-dirs.sh
sudo bash g90-image/scripts/prepare-lxmd-dirs.sh
```

## verify

```bash
ls -la /home/pi/.reticulum /home/pi/.lxmd
# expected: both dirs present, owned by pi:pi
```

```bash
# 5. (OPTIONAL — only if using piardopc / digipify stack)
sudo mkdir -p /home/pi/ardop
sudo cp g90-launcher/systemd/ardop-ptt-bridge.service /etc/systemd/system/
sudo cp g90-launcher/systemd/piardopc.service /etc/systemd/system/
sudo cp g90-launcher/scripts/ardop_ptt_bridge.py /home/pi/ardop/
sudo chmod +x /home/pi/ardop/ardop_ptt_bridge.py
# piardopc binary: either build from source on the Pi 5
# (32-bit ARMhf binaries won't run — Pi 5 has no 32-bit mode),
# or grab a prebuilt aarch64 binary from the upstream project.
# Place it at /home/pi/ardop/piardopc
```

## verify

```bash
ls -la /etc/systemd/system/{ardop-ptt-bridge,piardopc}.service \
       /home/pi/ardop/ardop_ptt_bridge.py
# expected: 3 files (only if you completed the optional block)
```

```bash
# 6. (OPTIONAL — only if you want the askpass wrapper for g90
# ssh access from the dev Pi)
sudo mkdir -p /home/pi/.local/bin
sudo cp g90-image/config/askpass-g90.sh /home/pi/.local/bin/askpass-g90.sh
sudo chmod 600 /home/pi/.local/bin/askpass-g90.sh
```

## Step 5 — Configure operator values

Edit `/etc/reticulumhf/config.env` and set:

- `RETICULUMHF_AP_SSID` — your wifi network name (e.g.
  `g90digi` or your callsign)
- `RETICULUMHF_AP_PASS` — wifi password (**CHANGE_ME →
  your password**; min 8 chars)
- `RETICULUMHF_AP_CHANNEL` — 1-11 (default 7)
- `RADIO_ID` — `xiegu_g90` or `qyt_kt8900d`
- `SERIAL_PORT` — your FTDI cable (usually `/dev/ttyUSB0`)
- `AUDIO_CARD` — your Digirig's USB audio card number
  (`arecord -l` to find it)

Edit `/etc/hostapd/hostapd.conf` if you need different wifi
parameters than the default.

Edit `~/.config/pat/config.json` and set:

- `callsign` — your amateur radio callsign (NOT `N0CALL`)
- Any other personal values

## Step 6 — Enable + start services

```bash
sudo systemctl daemon-reload

# Our overlay services (the ones this repo provides):
sudo systemctl enable --now \
    g90-shared-launcher.service \
    meshchatx.service \
    lxmd.service \
    pat-http.service \
    zerotier-one.service

# Optional: only if using piardopc / digipify
sudo systemctl enable --now \
    ardop-ptt-bridge.service \
    piardopc.service \
    rigctld.service

# Note: reticulumhf-portal.service starts the box-level web UI on
# port 80, and reticulumhf-rnsd.service starts the Reticulum
# network stack daemon. freedvtnc2 is a pipx binary (no
# systemd unit; runs as a foreground process when launched
# by the launcher FreeDV TUI row). All three are required by
# the manifest's component check; verify they're up (Step 7).

# IMPORTANT: restart the launcher after a working tree change.
# The systemd service starts on box boot with whatever code
# was on disk at that moment. If you just ran `git checkout
# -f v0.6.18` in Step 1a, the service needs an explicit
# restart to pick up the new code:
sudo systemctl restart g90-shared-launcher.service
```

## verify (immediately, before moving on)

```bash
for svc in g90-shared-launcher.service meshchatx.service lxmd.service \
           pat-http.service zerotier-one.service reticulumhf-rnsd.service \
           reticulumhf-portal.service; do
    state=$(systemctl is-active "$svc" 2>&1)
    echo "$svc: $state"
done
# expected: every line says "active"
# if any says "inactive" or "failed", stop and diagnose that
# one before continuing.
```

```bash
sudo zerotier-cli info
# expected: 200 info <node-id> 1.16.2 ONLINE
```

## Step 7 — Verify

After reboot, confirm everything is up:

```bash
# Shared launcher (the page your wifi clients bookmark)
curl -sI http://<hostname>.local/ | head -3
# Expected: HTTP/1.1 200 OK

# Launcher version + component check (the canonical health endpoint)
curl -s http://<hostname>.local/launcher-status
# Expected: "Your version: v0.6.18" / "Latest: v0.6.18 (you're up to date)"
# Expected: "All components match v0.6.18." — every unit active, every
# config file present, every pipx venv at the manifest's min_version.
# If anything is missing, the component list shows ✗ next to the
# missing unit / file / package.
```

## Verification table (run before declaring the build done)

Run each command. Every line should match the expected output.

| Check | Command | Expected |
|---|---|---|
| Bookworm base | `cat /etc/os-release \| grep PRETTY` | `Raspbian GNU/Linux 12 (bookworm)` |
| aarch64 | `uname -m` | `aarch64` |
| Launcher working tree | `cd /home/pi/shared_launcher && git describe --tags` | `v0.6.18` |
| Launcher service | `systemctl is-active g90-shared-launcher` | `active` |
| meshchatx | `systemctl is-active meshchatx` | `active` |
| lxmd | `systemctl is-active lxmd` | `active` |
| pat-http | `systemctl is-active pat-http` | `active` |
| zerotier-one | `systemctl is-active zerotier-one` | `active` |
| reticulumhf-rnsd | `systemctl is-active reticulumhf-rnsd` | `active` |
| reticulumhf-portal | `systemctl is-active reticulumhf-portal` | `active` |
| modems73 binary | `file /usr/bin/modem73` | `ELF 64-bit LSB executable, ARM aarch64` |
| lxmd binary | `command -v lxmd` | `/home/pi/.local/bin/lxmd` |
| meshchatx binary | `command -v reticulum-meshchatx` | `/home/pi/.local/bin/reticulum-meshchatx` |
| freedvtnc2 binary | `command -v freedvtnc2` | `/home/pi/.local/bin/freedvtnc2` |
| zerotier-cli | `command -v zerotier-cli` | `/usr/bin/zerotier-cli` |
| ZT identity | `sudo zerotier-cli info` | `200 info <10-char hex> 1.16.2 ONLINE` |
| /launcher-status | `curl -s http://<host>/launcher-status \| grep -E 'version\|components'` | `Your version: v0.6.18` + `All components match v0.6.18.` |
| pat web UI | `curl -sI http://<host>:5000/` | `HTTP/1.1 200 OK` |
| FreeDV TNC port | `ss -lnt \| grep 8001` | `LISTEN ... 0.0.0.0:8001 ...` |
| Audio dirs | `ls /home/pi/.lxmd /home/pi/.reticulum` | both present, owned by pi:pi |

If any check fails, **stop and fix that check before continuing.**

## Step 8 — (Optional) Capture the image

Once everything is working and you've customized for your
deployment, you can capture the SD card / USB drive as a
reproducible image:

```bash
# On the laptop, with the SD card / USB drive plugged in:

# 1. dd the drive
sudo dd if=/dev/sdX of=g90digi-<date>-<label>.img bs=4M status=progress conv=fsync

# 2. Shrink it (pishrink from https://github.com/Drewsif/PiShrink)
#    pishrink handles e2fsck, resize2fs -M, truncate, and adds
#    /etc/rc.local expansion so rootfs fills the next drive.
pishrink.sh -Z g90digi-<date>-<label>.img

# 3. xz-compress for distribution
xz -T0 -6 g90digi-<date>-<label>.img
# Resulting file: g90digi-<date>-<label>.img.xz (~1 GB for a
# 6 GB pishrunk image; use -T0 -6 instead of -9 for ~3x
# faster compression with ~5% larger output)
```

The captured image is **dual-arch** — the same `.img.xz` boots
on Pi 4 or Pi 5 (64-bit mode) without modification, because it
ships both `kernel_2712.img` and `kernel8.img` plus matching
kernel modules.

## What's not in this recipe

- **Group-specific values** (SSID, password, callsign, ZT
  network ID) — your deployment, your values. Defaults are
  placeholders; you must replace them.
- **The captured `.img.xz` binary** — we don't ship it in
  github (1 GB is too big for git + we don't have release
  infrastructure wired up). Build it from this recipe.
- **patmenu2 source** — it's a clone of an external project
  with our edits layered on top. We don't redistribute the
  upstream. Clone it yourself and apply our
  `patmenu2-edits/start-pat-ardop` patch.
- **The dev Pi's "dev launcher on :9090"** — the design for
  this is captured in `.tmp/openclaw-spikes/two-launchers/README.md`
  but not yet implemented. The patmenu2 and dev-launcher
  features both depend on a working Pat/ARDOP feature path
  that hasn't been end-to-end verified.

## Getting help

- **For the launcher itself:** each app button in the web UI
  has a help link (tap the app name).
- **For build problems:** open an issue at
  <https://github.com/smeshT/reticulumpi/issues>
- **For ReticulumHF base problems:** see the
  [Light Fighter resources](https://lightfightermanifesto.org/resources/)
  or the [ReticulumHF repo](https://github.com/LFManifesto/ReticulumHF).
- **For Pi 5 specific gotchas:** see `memory/g90-project.md`
  in this repo for the 2026-08-09 dual-arch verification
  notes.

## Credits

The real work here is glue. This overlay exists because other
people built the hard parts first:

- The [ReticulumHF](https://github.com/LFManifesto/ReticulumHF)
  base image and [freedvtnc2](https://github.com/LFManifesto/freedvtnc2)
  by [Light Fighter Manifesto](https://lightfightermanifesto.org/).
- The [Reticulum](https://github.com/markqvist/Reticulum) network
  stack, [LXMF](https://github.com/markqvist/LXMF),
  [Sideband](https://github.com/markqvist/Sideband), and
  [NomadNet](https://github.com/markqvist/NomadNet) by Mark Qvist.
- [codec2](https://github.com/drowe67/codec2) by David Rowe
  (drowe67) — the codec family underlying freedvtnc2's data
  modes (DATAC1/DATAC3/DATAC4). The FreeDV voice-mode app is a
  separate project; this image uses the data modes via freedvtnc2.
- [Hamlib](https://github.com/Hamlib/Hamlib) for rig control.
- [flrig](https://github.com/w1hkj/flrig) by W1HKJ.
- [pat](https://github.com/la5nta/pat) by LA5NTA (Winlink).
- [fldigi](https://github.com/wizhippo/fldigi-flrig) (W1HKJ et al.),
  [WSJT-X](https://sourceforge.net/projects/wsjt/) (Joe Taylor K1JT
  et al.), and
  [JS8Call](https://github.com/JS8Call-improved) (Jordan Sherer
  KN4CRD et al.).
- [Raspberry Pi OS](https://www.raspberrypi.com/software/) for the
  foundation.
- [ZeroTier](https://www.zerotier.com/) for the overlay network.
- [modem73](https://github.com/RFnexus/modem73) (RFnexus) for
  the OFDM modem.

Full credits in the top-level [README.md](README.md#credits).
