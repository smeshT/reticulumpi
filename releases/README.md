# Releases

This directory documents each captured flashable image produced by the
g90 / sbitx overlay. The actual `.img.xz` binaries are attached as
GitHub Release assets (https://github.com/smeshT/reticulumpi/releases)
because they're ~1 GB each — too large for git.

## Index of releases

- **[2026-08-09 — pi5-g90digi-8-9-26](./2026-08-09-post-pi5-firstboot)**
  First fully-overlaid image. Captured live from the g90digi Pi 5.
  MD5 `a20ead9a6ec7914c6c4d9f35052bd446`. Boots Pi 4 (64-bit) and
  Pi 5 (dual-arch). Post the dual-arch verification of 2026-08-09.

## Adding a new release

1. `mkdir -p releases/<date>-<label>`
2. Drop the `.img.xz.manifest` (with MD5, size, source commit, label)
   in that directory
3. Write a brief NOTES.md describing what this release is for
4. Commit + push to git (NOT the `.img.xz` itself, that's an asset)
5. On github, run `gh release create <tag> -t "<label>" --notes-file=...`
   and attach the `.img.xz` as a release asset

# reticulumpi

Pi 4 + Pi 5 dual-arch (64-bit) Raspberry Pi image with Reticulum + FreeDV digital modes, pre-configured for the g90 / QYT KT-8900D mobile radio fleet.

## First-boot defaults (the public release baseline)

- **Default user:** `pi`
- **Default password:** `hfp123` ⚠️ **change this on first boot** via `sudo passwd pi`
- **Default hostname:** `g90digi`
- **Default AP SSID:** `g90digi`
- **Default AP password:** `CHANGE_ME` ⚠️ **set this in `g90-image/config/hostapd.conf` before flashing** (or change at first boot)
- **Default ZeroTier:** none (operators add their network ID via the overlay's `bootstrap.sh`)

These defaults are the public-release baseline. The actual values used
by a deployed fleet are operator-specific and live in the private
`g90-fleet-config.git` repo (see the `Repo layout` note below).

## What's in the box

- **Raspberry Pi OS Bookworm (aarch64)** base
- **Reticulum Network Stack** (rnsd, meshchat, freedvtnc2) — disabled at boot, started via the shared launcher
- **FreeDV TNC** for HF digital modes
- **PAT / pat-winlink** for ARDOP winlink email
- **g90 shared launcher** (Flask, port 8090) — web UI for managing services
- **node-portal** (Flask, port 80) — wifi captive portal
- **Pi 4 + Pi 5 dual boot** (kernel8.img + kernel_2712.img, arm_64bit=1)
- Pre-configured for the g90 / QYT KT-8900D radio:
  - Hostname `g90digi`
  - SSID `g90digi` (AP, channel 7, password `CHANGE_ME`)
  - ZeroTier network `<your-ZT-network-id>` (auto-join on boot)

## Quick start

### Flash

Download the latest `.img.xz` from the [Releases](../../releases) page.

```bash
# Decompress + dd to USB drive / SD card
xzcat reticulumpi-YYYY-MM-DD-post-overlay.img.xz | sudo dd of=/dev/sdX bs=4M conv=fsync status=progress
```

Replace `/dev/sdX` with your target device (use `lsblk` to find it). ⚠️ `dd` overwrites the target device — pick the right one.

Or use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) with "Use custom" → select the `.img.xz` file directly.

### First boot

1. Plug the USB drive / SD card into a Raspberry Pi 4 or Pi 5 (64-bit only)
2. Power on. The box boots, expands the rootfs to fill the drive, and reboots (~30 seconds)
3. After reboot, the box is online:
   - **LAN**: DHCP, mDNS `g90digi.local`
   - **WiFi AP**: SSID `g90digi`, password `CHANGE_ME`, channel 7
   - **Captive portal**: `http://192.168.4.1/` (when connected to the AP)
   - **Shared launcher**: `http://g90digi.local:8090/`
   - **ZeroTier**: `<your-ZT-IP>` (after ZT joins; takes ~30s)

### SSH access

```bash
ssh pi@g90digi.local
# password: hfp123 (Pi Imager default — CHANGE THIS for security)
```

Or via ZeroTier if you're on the same network:
```bash
ssh pi@<your-ZT-IP>
```

### Starting Reticulum / digital modes

Reticulum is **disabled at boot** (per project policy). Use the shared launcher's "Reticulum Stack: Start" button, or:

```bash
ssh pi@g90digi.local
sudo systemctl start reticulumhf-rnsd reticulum-meshchat
# freedvtnc2 only works if the G90 + Digirig are plugged in
sudo systemctl start freedvtnc2
```

## Hardware

- **Pi 4 / Pi 5** (tested: Pi 4 Model B, Pi 5 2GB)
- **G90 / QYT KT-8900D** radio
- **Digirig Mobile** sound card (USB)
- **FTDI cable** for CAT control (USB)
- **SanDisk Ultra Fit** USB drive (28 GB minimum)

## Customizing

### Change hostname / AP password / ZT network

Edit the image before first boot:

```bash
# Mount the boot partition
sudo mount -o loop,offset=$((8192 * 512)) reticulumpi-*.img /mnt

# Edit config files
sudo sed -i 's/g90digi/<your-hostname>/g' /mnt/cmdline.txt
# For AP password: edit /etc/hostapd/hostapd.conf on the rootfs
# For ZT network: edit /etc/systemd/system/zerotier-one.service.d/join.conf
```

### Rebuild from source

The image is built on top of [ReticulumHF](https://github.com/reticulumrf/reticulumhf-base), with our g90 overlay layered on top. See `g90-launcher.git` and `g90-image-Pi5.git` for the overlay sources.

```bash
# Pull the latest overlay
git clone https://github.com/smeshT/g90-launcher.git
git clone https://github.com/smeshT/g90-image-Pi5.git

# Build the image with pi-gen + the overlay
# (build script TBD — for now, see memory/g90-project.md in the
# reticulumpi project)
```

## Compatibility

**Verified architectures:**
- ✅ Raspberry Pi 4 Model B (aarch64, kernel8.img)
- ✅ Raspberry Pi 5 2GB (aarch64, kernel8.img or kernel_2712.img)

**Caveats:**
- **64-bit only** — won't boot in 32-bit mode. Pi 4 supports 64-bit fine.
- For a **different Pi 4 box** (not g90digi), you'll want to regenerate:
  - SSH host keys: `sudo rm /etc/ssh/ssh_host_* && sudo ssh-keygen -A`
  - ZeroTier identity: `sudo systemctl stop zerotier-one && sudo rm /var/lib/zerotier-one/identity.* && sudo systemctl start zerotier-one`
- The default Pi Imager password `hfp123` is baked in. **Change it** for production.

## Project notes

This image is the work of multiple iterations on the g90 / sbitx fleet. See the [g90 project notes](https://github.com/smeshT/reticulumpi/blob/main/NOTES.md) for the full deploy history, lessons learned, and policy documentation.

## License

TBD — currently experimental.
