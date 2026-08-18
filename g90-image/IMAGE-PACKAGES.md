# Image packages

> **What this file is:** the list of apt packages this image
> overlay REQUIRES on top of the ReticulumHF base image.
> Run these after the ReticulumHF setup wizard completes
> (or as part of a `bootstrap.sh` for fleet deploys).
>
> **Why it's a separate file:** the g90 image overlay is a
> **recipe**, not a build pipeline — there's no Dockerfile,
> no Ansible, no Makefile. The packages below are added
> by the operator (or a deploy script) after the base image
> boots for the first time. Tracking them in one place
> means the next image capture has them, and the next
> operator knows what to install.

## Required packages (apt)

| Package | Why we need it | Added when |
|---|---|---|
| `xterm` | Terminal client for the FreeDV TUI on the noVNC desktop. `lxterminal` is NOT installed on the ReticulumHF base image (it ships LXDE-free: just Xvfb + openbox + x11vnc). Switched from `lxterminal` → `xterm` on 2026-08-17 after the Start button silently failed because `lxterminal` was missing. Verified working on g90digi (Pi 5, ReticulumHF base, 2026-08-17 18:14 MDT). | 2026-08-17 |

## Already on the base image (don't reinstall)

These come with the ReticulumHF base and we rely on them;
re-installing them is harmless but wastes bandwidth:

- `xvfb` (the virtual display backing noVNC)
- `x11vnc` (VNC server)
- `websockify` (noVNC websocket bridge)
- `openbox` (window manager for the Xvfb desktop)
- `fonts-dejavu-core` (provides DejaVu Sans Mono — the TrueType font xterm uses; xterm's default bitmap font is NOT shipped)
- `python3` (the launcher + node-portal + freedvtnc2 runtime)
- `pipx` + `freedvtnc2` (the KISS TNC)
- `rigctld` (hamlib, CAT control)
- `zerotier-one` (ZT network join)
- `hostapd`, `dnsmasq` (the g90digi AP)

## Apt install command (reference)

```bash
sudo apt-get update
sudo apt-get install -y xterm
```

## Verification

After installing on a fresh image:

```bash
xterm -fa "DejaVu Sans Mono" -fs 10 -T test -e "echo OK; sleep 2"
```

If a window titled "test" appears in the noVNC tab (`:6080`)
and prints `OK`, the install is complete.
