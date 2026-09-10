# reticulumpi — project notes

This document captures the deploy history, lessons learned, and policy documentation for the g90 / sbitx HF-radio fleet's Pi image work.

Last major work: **2026-08-09**.

## Hardware context

- **Pi 4 / Pi 5** running ReticulumHF + g90 overlay + digital-mode stack (PAT, ARDOP, FreeDV)
- **G90 / QYT KT-8900D** mobile radio
- **3 HF radios total** in the fleet: g90digi (Pi 5), g90f1r2 (Pi 4), sbitx (SoftRock-style HF rig on a Pi)
- Cross-pollinating audio/digimode/Reticulum setup

## Image policy (revised 2026-08-09)

**One canonical image, two deployment targets** (Pi 4 + Pi 5 in 64-bit mode). Both architectures can boot the same image because:

- The boot partition ships with both `kernel_2712.img` (Pi 5 only) AND `kernel8.img` (universal aarch64)
- `config.txt` has `arm_64bit=1` (forces 64-bit boot)
- The rootfs has both `/lib/modules/6.6.51+rpt-rpi-2712/` AND `/lib/modules/6.6.51+rpt-rpi-v8/`
- Both Pi 4 DTBs (`bcm2711-rpi-4-b.dtb`) and Pi 5 DTBs (`bcm2712-rpi-5-b.dtb`) are present
- Both Pi 4 firmware (`start4*.elf`) and Pi 5 firmware (`start*.elf`) are present

So: don't maintain separate Pi 4 + Pi 5 images.

## Image shrink pipeline

```
laptop:
  dd if=/dev/sda of=~/work/<radio>-<date>.img bs=4M conv=fsync status=progress

dev pi (nomadpi):
  scp ~/work/<radio>-<date>.img.gz pi@nomadpi:/media/pi/REMOTE/pi_images/
  sudo pishrink -Z /media/pi/REMOTE/pi_images/<radio>-<date>.img
  # 28 GB raw → 6 GB after pishrink → 1 GB after xz -T0 -6
```

`pishrink` does:
1. `e2fsck -f` (fix live-dd inconsistencies)
2. `resize2fs -M` (shrink rootfs to minimum)
3. `parted` resize + truncate (image = used space only)
4. `xz -9` (compress; use `xz -T0 -6` for ~3x faster with ~5% larger output)

## Lessons learned (2026-08-09)

- **`zerofree` is required before dd'ing the source.** pishrink's resize2fs -M still works on a live-captured image, but the .img.xz is ~25% larger without zerofree.
- **`xz -9` is slow on a 4-core Pi** — use `xz -T0 -6` instead (~25 min for 6 GB instead of 2-3 hours).
- **Detach long-running exec calls** with `setsid + nohup + &`. A 30-min `dd` got killed by an OpenClaw tool policy change.
- **Pi 5's USB-C power negotiation can fail** with some USB drives during sustained writes. Two different USB drives failing Pi Imager's "error reading from storage" in two days = symptom, not cause. Workarounds: dd from laptop, powered USB hub, or USB 2.0 black ports.
- **ZeroTier systemd service needs `ExecStartPost=/bin/sleep 2`** before `zerotier-cli join` — otherwise the join races the daemon's socket listener and fails.
- **g90digi Pi 5 BOOT_ORDER=0x4** (USB only) — no SD card fallback. USB drive is the only boot media.

## Image manifest convention

Each backup gets a sidecar `.manifest`:

```
# Image manifest
radio:      g90digi
hostname:   g90digi
label:      post-overlay-shrunk
date:       2026-08-09
source:     g90digi:/dev/sda (Pi 5 2GB, SanDisk Ultra Fit 28 GB)
output:     pi5-g90digi-8-9-26.img.xz
output_md5: a20ead9a6ec7914c6c4d9f35052bd446
output_size_bytes: 1034088336 (986 MB)
compress:   xz -T0 -6 (parallel, level 6)
notes:      First fully-overlaid image. Boots Pi 4 (64-bit) AND Pi 5.
```

## File inventory

- `README.md` — quick-start + flashing instructions
- `NOTES.md` — this file (deploy history, lessons, policy)
- `pi5-g90digi-8-9-26.img.xz` — current image (post-overlay, dual-arch)
- `g90digi-2026-08-08-post-pi5-firstboot.img.xz` — earlier image (post-firstboot, dual-arch)
- `*.manifest` — sidecar manifests for each image

## Related repos

- [g90-launcher](https://github.com/smeshT/g90-launcher) — Flask app + systemd units + ARDOP bridge (shared across fleet)
- [g90-image-Pi5](https://github.com/smeshT/g90-image-Pi5) — Pi 5-specific overlay (hostname, AP, Reticulum config)
- [reticulumpi](https://github.com/smeshT/reticulumpi) — this repo (images + releases)
