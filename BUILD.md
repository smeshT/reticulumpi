# Building a g90 box from source

This is the **end-to-end recipe** for building a g90 box
(Raspberry Pi 4 or Pi 5 running the g90digi image, configured
for a Xiegu G90 / QYT KT-8900D HF radio) starting from a
stock ReticulumHF base image.

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
   - **mDNS:** `ssh pi@g90digi.local` (or whatever hostname
     you set)
   - **LAN IP:** check your router's admin page, or use
     `nmap -sn 192.168.1.0/24` (replace with your subnet)
   - **AP:** the Pi broadcasts a `ReticulumHF` wifi network
     (default password on the printed card in the box). Connect
     to it; the Pi is at `192.168.4.1`.
4. SSH in: `ssh pi@g90digi.local` (or LAN IP).
5. Run `sudo apt update && sudo apt upgrade -y` and reboot.
   This pulls the latest package versions. (~10-15 min on Pi 4)

## Step 3 — Install overlay packages

```bash
# On the g90 box, as the pi user:

# apt packages
sudo apt install -y \
    git curl wget xz-utils \
    python3 python3-pip python3-venv \
    flrig hamlib pat \
    direwolf \
    avahi-daemon avahi-utils \
    zerotier-one

# pipx (for freedvtnc2 and other Python tools)
sudo apt install -y pipx
pipx ensurepath

# freedvtnc2 (FreeDV TNC for HF digital modes)
pipx install freedvtnc2

# reticulum-meshchat (mesh UI on top of Reticulum)
git clone https://github.com/markqvist/reticulum-meshchat.git \
    /home/pi/reticulum-meshchat
```

**Note on direwolf:** As of 2026-08, the apt `direwolf` package
is built for the Pi 4. For Pi 5 (aarch64 only), you may need
to build from source or skip ARDOP/direwolf if your workflow
doesn't need them.

**Note on piardopc:** The g90f1r2 digipify work uses a 32-bit
ARMhf `piardopc` binary that won't run on Pi 5 (no 32-bit ARM
mode). Newer Pi 5 builds use `pat` directly with rigctld for
PTT — no piardopc needed. If you want digipi's ARDOP stack,
build piardopc from source on the Pi 5 or use the cross-compile
recipe in `g90-launcher/systemd/install.sh` notes.

## Step 4 — Apply the overlay

```bash
# On the g90 box:

# 1. Clone this repo
cd /home/pi
git clone https://github.com/smeshT/reticulumpi.git shared_launcher
cd shared_launcher

# 2. Copy the overlay config files into place
sudo cp g90-image/config/reticulumhf-config.env /etc/reticulumhf/config.env
sudo cp g90-image/config/hostapd.conf /etc/hostapd/hostapd.conf
sudo cp g90-image/config/pat-config.json /home/pi/.config/pat/config.json
sudo cp g90-image/config/start-novnc-session /usr/local/bin/start-novnc-session
sudo chmod +x /usr/local/bin/start-novnc-session
sudo cp g90-image/systemd-units/g90-shared-launcher.service /etc/systemd/system/
sudo cp g90-image/systemd-units/pat-http.service /etc/systemd/system/
sudo cp g90-image/patmenu2-edits/start-pat-ardop /home/pi/patmenu2/start-pat-ardop
chmod +x /home/pi/patmenu2/start-pat-ardop

# 3. Install the ARDOP PTT bridge (optional — only if using
#    piardopc / digipify stack)
sudo mkdir -p /home/pi/ardop
sudo cp g90-launcher/systemd/ardop-ptt-bridge.service /etc/systemd/system/
sudo cp g90-launcher/systemd/piardopc.service /etc/systemd/system/
sudo cp g90-launcher/scripts/ardop_ptt_bridge.py /home/pi/ardop/
sudo chmod +x /home/pi/ardop/ardop_ptt_bridge.py
# piardopc binary: either build from source on the Pi 5
# (32-bit ARMhf binaries won't run — Pi 5 has no 32-bit mode),
# or grab a prebuilt aarch64 binary from the upstream project.
# Place it at /home/pi/ardop/piardopc

# 4. (Optional) Install the askpass wrapper for g90 ssh access
sudo mkdir -p /home/pi/.local/bin
cp g90-image/config/askpass-g90.sh /home/pi/.local/bin/askpass-g90.sh
chmod 600 /home/pi/.local/bin/askpass-g90.sh
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
    pat-http.service

# ZeroTier (installed by apt, needs joining — see below)
sudo systemctl enable --now zerotier-one.service

# Optional: only if using piardopc / digipify
sudo systemctl enable --now \
    ardop-ptt-bridge.service \
    piardopc.service \
    rigctld.service

# Note: reticulumhf-portal.service, reticulumhf-rnsd.service,
# freedvtnc2, and the AP are pre-installed by the ReticulumHF
# base image and start automatically on boot. You don't need
# to enable them — just verify they're up (Step 7).
```

For ZeroTier, join your network:

```bash
sudo zerotier-cli join <your-network-id>
# Approve the node in your ZT central controller's web UI
```

## Step 7 — Verify

After reboot, confirm everything is up:

```bash
# Shared launcher (the page your wifi clients bookmark)
curl -sI http://g90digi.local/ | head -3
# Expected: HTTP/1.1 200 OK

# pat web UI
curl -sI http://g90digi.local:5000/ | head -3
# Expected: HTTP/1.1 200 OK

# rigctld (CAT control)
echo "get_freq" | nc -q 1 g90digi.local 4532
# Expected: 14074000   (or whatever your radio is on)

# ZeroTier
sudo zerotier-cli listnetworks
# Expected: <your-network-id>  OK  ...

# FreeDV TNC
ss -lnt | grep 8001
# Expected: LISTEN ... 0.0.0.0:8001 ...
```

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
- [codec2](https://github.com/drowe67/codec2) /
  [FreeDV](https://github.com/drowe67/codec2/blob/main/README_data.md)
  by David Rowe (drowe67).
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

Full credits in the top-level [README.md](README.md#credits).
