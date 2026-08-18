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
| `pulseaudio` | Sound server backing the launcher audio apps (FLrig, fldigi, JS8Call, WSJT-X, FreeDV) and the `Reset Audio Devices` button. ReticulumHF ships `pavucontrol` and `~/.config/pulse/` config (verified 2026-08-09 capture on g90digi), but **the `pulseaudio` daemon package itself is NOT installed** — `pulseaudio.service` is referenced by `g90-waterfall.service` (`After=network-online.target pulseaudio.service`), and several launcher scripts (e.g. `start_pavucontrol.sh`) assume the server is running. Without it, apps fall back to direct ALSA only, pavucontrol shows no sinks, and the waterfall diagnostic tool's `After=` ordering silently degrades. Installed as part of the overlay recipe 2026-08-18. | 2026-08-18 |
| `pavucontrol` | GTK mixer that the launcher's `Start Pavucontrol` row spawns in the noVNC tab. ReticulumHF base ships `~/.config/pavucontrol.ini` (so it was clearly meant to run), but the `pavucontrol` package itself was missing on the 2026-08-09 Pi 5 capture and had to be installed manually. Listed as a required overlay package 2026-08-18 alongside `pulseaudio` because the launcher's audio rows assume both. | 2026-08-18 |

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
- `~/.config/pavucontrol.ini` and `~/.config/pulse/` (per-user config the setup wizard writes, but **the server package itself is not** — see required packages above)

## Apt install command (reference)

```bash
sudo apt-get update
sudo apt-get install -y xterm pulseaudio pavucontrol
```

> **Why pulseaudio and not pipewire?** The ReticulumHF base ships
> PulseAudio config (`~/.config/pulse/`) and the launcher's audio
> rows (FLrig/fldigi/JS8Call/WSJT-X/Pavucontrol/FreeDV) all assume
> PulseAudio semantics (`pavucontrol` → sink/source switching,
> `parec` / `pacat` from waterfall diagnostic tool). PipeWire's
> PulseAudio compatibility layer would also work, but the base
> image is PulseAudio-native, so we stay with that.

## Verification

After installing on a fresh image:

```bash
# xterm: opens a terminal in the noVNC :6080 desktop
xterm -fa "DejaVu Sans Mono" -fs 10 -T test -e "echo OK; sleep 2"

# pulseaudio: server is running, can list sinks
systemctl --user status pulseaudio.service || pulseaudio --check
pactl info | grep -E "Server Name|Server Version"

# pavucontrol: launches and shows the running PulseAudio sinks
pavucontrol --version
```

If a window titled "test" appears in the noVNC tab (`:6080`)
and prints `OK`, `pactl info` returns a server name, and
`pavucontrol --version` prints a version, the install is complete.
