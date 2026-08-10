# reticulumpi

Pi 4 / Pi 5 dual-arch Raspberry Pi image with Reticulum + FreeDVtnc2
digital modes, pre-configured for the g90 / QYT KT-8900D mobile
radio (will work with others but untested).

## Build your own

The `.img.xz` binary isn't shipped in this repo (1 GB is too big
for git + we don't have github release infrastructure wired up).
You build it yourself from this repo + a stock ReticulumHF base
image.

Full step-by-step recipe: **[`BUILD.md`](BUILD.md)**.

The short version: flash the [ReticulumHF](https://lightfightermanifesto.org/tools/reticulumhf/)
base image with Raspberry Pi Imager, `apt install` the overlay
packages (flrig, hamlib, pat, direwolf, zerotier, etc.), clone
this repo, drop `g90-image/` + `g90-launcher/` files into place,
set your operator values (callsign, SSID, password, ZT network)
in `/etc/reticulumhf/config.env`, enable the systemd units, reboot.
~45-60 min on a Pi 4, mostly package installation.

## What's here

- **`BUILD.md`** — the end-to-end build recipe (start here).
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
  the captured `.img.xz` files. See `releases/2026-08-09-post-pi5-firstboot/NOTES.md`
  for first-boot guidance on a pre-built image.
- **`g90-image/QUICK-START.html` / `.pdf`** — printable end-user
  manual for a deployed box.

## Operating a deployed box

If you already have a g90digi box flashed and want to use it:
see [`g90-image/QUICK-START.md`](g90-image/QUICK-START.md). It's
the end-user manual — what the buttons do, how to connect your
radio, what to do if something breaks.

For build problems: open an issue at
<https://github.com/smeshT/reticulumpi/issues>.

## Architecture

- **Pi 4 / Pi 5** (tested: Pi 4 Model B, Pi 5 2GB)
- **G90 / QYT KT-8900D** radio (will work with others but untested)
- **Digirig Mobile** sound card (USB)
- **FTDI cable** for CAT control (USB)
- **SanDisk Ultra Fit** USB drive (28 GB minimum)

## Project notes

The full deploy history, lessons learned, and policy documentation
is in `memory/g90-project.md`.

## License

TBD — currently experimental.
