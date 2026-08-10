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

The short version: download the
[ReticulumHF](https://github.com/LFManifesto/ReticulumHF/releases/)
base image (also linked from the
[Light Fighter resources](https://lightfightermanifesto.org/resources/)),
flash it with Raspberry Pi Imager, `apt install` the overlay
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

## Credits

This project stands on the shoulders of the open-source amateur
radio and mesh networking communities. Everything here is glue —
the real work lives in the projects below.

**Base layer — the ReticulumHF image:**
- [ReticulumHF](https://github.com/LFManifesto/ReticulumHF) by the
  [Light Fighter Manifesto](https://lightfightermanifesto.org/) —
  Reticulum + FreeDV over HF radio, packaged as a Raspberry Pi
  image.
- [freedvtnc2](https://github.com/LFManifesto/freedvtnc2) (also
  LFManifesto) — FreeDV TNC.

**Networking stack:**
- [Reticulum (RNS)](https://github.com/markqvist/Reticulum),
  [LXMF](https://github.com/markqvist/LXMF),
  [Sideband](https://github.com/markqvist/Sideband), and
  [NomadNet](https://github.com/markqvist/NomadNet) — all by
  Mark Qvist. The off-grid mesh layer.
- [ZeroTier](https://www.zerotier.com/) — overlay networking.

**Digital modes:**
- [codec2](https://github.com/drowe67/codec2) and
  [FreeDV](https://github.com/drowe67/codec2/blob/main/README_data.md)
  by David Rowe (drowe67) — the HF voice + data codec family.
- [pat](https://github.com/la5nta/pat) by LA5NTA — Winlink client
  (Go).

**CAT control + hamlib:**
- [Hamlib](https://github.com/Hamlib/Hamlib) — rig control library.
- [flrig](https://github.com/w1hkj/flrig) by W1HKJ — transceiver
  control application.

**Amateur radio apps (apt-installed by the ReticulumHF base + our
overlay):**
- [fldigi](https://github.com/wizhippo/fldigi-flrig) (W1HKJ et al.)
  — digital modes.
- [WSJT-X](https://sourceforge.net/projects/wsjt/) by Joe Taylor
  (K1JT) et al. — FT8, JT9, etc.
- [JS8Call](https://github.com/JS8Call-improved) — originally by
  Jordan Sherer (KN4CRD), now maintained as JS8Call-improved.

**Operating system:**
- [Raspberry Pi OS](https://www.raspberrypi.com/software/) (Bookworm
  aarch64) — the foundation.

If we forgot you, open an issue — we fix credits faster than docs.

## License

TBD — currently experimental.
