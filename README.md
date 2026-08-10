# reticulumpi

Pi 4 / Pi 5 dual-arch Raspberry Pi image with Reticulum + FreeDV
digital modes, pre-configured for the g90 / QYT KT-8900D mobile
radio fleet.

## What's here

- **`g90-image/`** — the canonical image overlay (Pi 4 + Pi 5 in
  64-bit mode). The dual-arch capability was verified on
  2026-08-09: one captured image deploys to both architectures.
  `g90-image/pi4/` is the Pi 4 historical, preserved for
  reference (read-only, not for new work).
- **`g90-launcher/`** — the shared launcher (Flask app on port 80
  on the deployed box), the systemd units, the ARDOP PTT bridge,
  the install script.
- **`scripts/`** — g90-specific scripts (`freedv_tui.sh`,
  `freedv_waterfall.py`, `g90-test-sled-setup.sh`,
  `start_waterfall.sh`, plus the `_lib_stop.sh` helper).
- **`memory/`** — the canonical reference (`g90-project.md`) and
  design notes (`2026-07-28-short-turn-router.md`).
- **`releases/`** — per-image-release docs (manifest, NOTES) for
  the captured `.img.xz` files. The binaries themselves live on
  the dev Pi at `/media/pi/REMOTE/pi_images/` (1 GB is too large
  for git); see `releases/2026-08-09-post-pi5-firstboot/NOTES.md`
  for download instructions.

## Companion repo

Group-specific configuration (SSID, password, callsign,
operating frequencies, ZeroTier network ID, deployed-box state)
lives in the private companion repo
[`smeshT/g90digi`](https://github.com/smeshT/g90digi). **This
public repo never has group-specific values** — only the
template, the overlay, and the build recipe.

## Quick start (for a fresh deploy)

This is the **recipe-only** path. The 1 GB binary isn't published
to github (too big for git + no release infrastructure wired up).
Build it from this repo + a stock ReticulumHF image — full
instructions in [`g90-image/QUICK-START.md`](g90-image/QUICK-START.md).

The **g90 group** (operators of the deployed fleet) has a pre-built
image available over ZeroTier — see the private companion repo at
[`smeshT/g90digi`](https://github.com/smeshT/g90digi) for the URL.
Public readers can't reach it.

```bash
# 1. Verify after download:
md5sum pi5-g90digi-8-9-26.img.xz
# expected: a20ead9a6ec7914c6c4d9f35052bd446

# 2. Flash to USB drive / SD card
xzcat pi5-g90digi-8-9-26.img.xz | sudo dd of=/dev/sdX bs=4M conv=fsync status=progress

# 3. Boot the Pi, log in (default pi / hfp123 — CHANGE THIS)
#    The shared launcher is at http://g90digi.local/
```

See `g90-image/QUICK-START.md` for the full first-boot guide.

## Building from source

The image is built on top of
[ReticulumHF](https://github.com/reticulumrf/reticulumhf-base),
with the `g90-image/` overlay layered on top. See the per-release
NOTES (`releases/<date>-<label>/NOTES.md`) for the build steps.

## Architecture

- **Pi 4 / Pi 5** (tested: Pi 4 Model B, Pi 5 2GB)
- **G90 / QYT KT-8900D** radio
- **Digirig Mobile** sound card (USB)
- **FTDI cable** for CAT control (USB)
- **SanDisk Ultra Fit** USB drive (28 GB minimum)

## Project notes

The full deploy history, lessons learned, and policy documentation
is in `memory/g90-project.md`. Daily session logs (operational,
with real ZT IPs and passwords) are in the private `smeshT/g90digi`
repo's `memory/` directory.

## License

TBD — currently experimental.
