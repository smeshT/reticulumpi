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
| `fldigi` | The `fldigi` binary that the launcher's FLDigi row spawns. ReticulumHF ships `~/.fldigi/fldigi_def.xml` and `fldigi.prefs` (per-user config, see 2026-08-09 capture in `memory/2026-08-09.md` around line 559-588), but **the `fldigi` package itself was missing** on that capture. Same "config-but-no-package" trap as pavucontrol. Without it, the FLDigi Start button errors with "command not found." Installed as part of the overlay recipe 2026-08-18. | 2026-08-18 |
| `js8call` | The `js8call` binary that the launcher's JS8Call row spawns. NOT in ReticulumHF base, but **IS in Debian bookworm arm64** (`js8call 2.2.0+ds-5`, verified on the 2026-08-09 capture). Bake into the recipe so the next operator doesn't have to apt-install it manually after the launcher's Start button errors. | 2026-08-18 |
| `wsjtx` | The `wsjtx` binary that the launcher's WSJT-X row spawns. Same story as `js8call`: NOT in ReticulumHF base, **IS in Debian bookworm arm64** (`wsjtx 2.6.1+repack-1`, verified 2026-08-09). Bake into the recipe. | 2026-08-18 |

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

## Digimode apps (apt) — also required

These are the audio-side apps the launcher's rows spawn. Not
in ReticulumHF base; must be apt-installed after first boot.
ReticulumHF **does** ship the per-user config
(`~/.flrig/Xiegu-G90.prefs`, `~/.fldigi/fldigi_def.xml`,
`~/.config/JS8Call.ini`, `~/.config/WSJT-X.ini`,
`~/.config/pat/config.json`), so the apps were clearly
meant to run on this image — but the binaries themselves
are not on the base. Same "config-but-no-package" trap as
`pavucontrol` / `pulseaudio`.

| Package | Why we need it | Source |
|---|---|---|
| `flrig` | The hamlib GUI rig controller the launcher's FLrig row spawns | Debian `flrig` |
| `fldigi` | The multi-mode digimode app the launcher's FLDigi row spawns | Debian `fldigi` |
| `js8call` | The FT8/JS8 app the launcher's JS8Call row spawns | Debian `js8call` (bookworm arm64: `2.2.0+ds-5`) |
| `wsjtx` | The FT8/WSPR app the launcher's WSJT-X row spawns | Debian `wsjtx` (bookworm arm64: `2.6.1+repack-1`) |
| `pat` | The Winlink client the launcher's Pat row spawns | Debian `pat` |

## Apt install command (reference)

```bash
sudo apt-get update
sudo apt-get install -y \
    flrig fldigi js8call wsjtx pat \
    xterm pulseaudio pavucontrol
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

# fldigi / js8call / wsjtx: each binary is on PATH
for b in fldigi flrig js8call wsjtx pat; do
    command -v "$b" >/dev/null && echo "OK: $b" || echo "MISSING: $b"
done
```

If a window titled "test" appears in the noVNC tab (`:6080`)
and prints `OK`, `pactl info` returns a server name,
`pavucontrol --version` prints a version, and the for-loop
prints `OK:` for every binary, the install is complete.
