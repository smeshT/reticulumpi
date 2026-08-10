# g90-image/pi4 — Pi 4 historical overlay

This directory holds the **Pi 4 historical** overlay — the
original QYT KT-8900D / G90 image overlay for the Pi 4 (BCM2711).
It's preserved for reference and as the lineage of how this
project got here.

## What's here

- `config/` — askpass-g90.sh, hostapd.conf (g90f1r2-AP),
  pat-config.json, reticulumhf-config.env (g90f1r2-AP),
  start-novnc-session
- `node-portal/` + `node-portal-templates/` — the wifi
  captive portal (port 80)
- `patmenu2-edits/start-pat-ardop` — the pat launch wrapper
- `systemd-units/` — g90-shared-launcher.service, pat-http.service
- `README.md`, `QUICK-START.md` — the Pi 4 era docs

## What's NOT here (was missing even in the Pi 4 era)

- `piardopc-binary/` — the 32-bit ARMhf ARDOP softmodem binary
  was kept in `/home/pi/.openclaw/workspace/g90-image/piardopc-binary/`
  in the work tree but was never committed to the repo. It's
  now in `smeshT/g90digi/bin/piardopc` per the 2026-08-10
  repo cleanup.
- `print-styles.css` — generated for the QUICK-START.pdf; not
  version-controlled.
- `node-portal/templates/` (symlink to `node-portal-templates/`)
  — was a symlink artifact, not committed.
- `__pycache__/` — Python bytecode, never committed.
- `*.bak-20260707-*` — local backups from the 2026-07-07 edits,
  not committed.

## Why this is "historical"

Per the 2026-08-09 dual-arch verification (`memory/g90-project.md`
→ "Image policy and dual-arch compatibility"), the same captured
image deploys to both Pi 4 (64-bit mode) and Pi 5. The
**canonical** recipe is now at `g90-image/` (one level up from
this directory), with the dual-arch kernel handling in the
captured image (kernel8.img + kernel_2712.img side by side,
arm_64bit=1 in config.txt).

What's in this `pi4/` directory is the Pi 4 overlay as it
existed before the dual-arch policy was finalized. It uses
`g90f1r2-AP` as the SSID and references the port-80/8090 launcher
split that was current in mid-2026. The current `g90-image/` is
the same content with the g90digi-AP rename applied and the
group-specific values neutralized.

## If you need to revert to the Pi 4 era

Don't. The Pi 4 era overlay is here for archeology, not for
deployment. If you need a Pi 4 deployment, use the canonical
`g90-image/` and the dual-arch captured image (one image, both
targets). The Pi 4-specific differences (older 32-bit-friendly
configs, the g90f1r2-AP SSID rename) are documented in the
git history of this directory and recoverable from there if
needed.

## Status

- Last meaningful update: 2026-07-08 (the g90f1r2 deployment)
- Frozen: 2026-08-10 (renamed `g90-image-pi5/` → `g90-image/`,
  `g90-image/` → `g90-image/pi4/`)
- Maintained: NO. Read-only from here.
