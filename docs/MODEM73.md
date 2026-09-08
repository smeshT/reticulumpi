# Modem73 recipe — Reticulum-over-OFDM on HF

Modem73 is the OFDM software modem ([RFnexus/modem73]) for HF/VHF/UHF
radios. It's the third digital-mode modem in this fleet alongside
FreeDVtnc2 (audio codec) and ARDOP/winlink (HF email). Modem73 runs
headlessly on the g90 box and bridges a Reticulum TCP interface to
the HF channel.

This doc covers: install, config, Reticulum interface wiring, and
launcher integration (TUI + headless-loopback modes + audio reset).

[RFnexus/modem73]: https://github.com/RFnexus/modem73

## When to use modem73 vs the other modems

| Modem | Mode | What it does |
|---|---|---|
| **freedvtnc2** | interactive TUI + Reticulum KISS | HF digital voice codec, frees up the radio for voice QSOs |
| **ARDOP / pat-winlink** | always-on daemon | HF email (Winlink) |
| **modem73** | headless or interactive TUI | HF data OFDM modem (MFSK/OFDM/RDM), Reticulum transport |

Pick modem73 when you want a low-overhead Reticulum transport over
HF that's independent of FreeDV voice codec (so you can have both a
voice QSO and data going on without one interfering with the other).
Modem73 has no voice path, so it can share the radio with js8call /
wsjtx / fldigi etc.

## Install

```bash
# Modem73 is on PyPI
pip install modem73
# or pipx for an isolated venv (recommended)
pipx install modem73

# Verify
modem73 --help
modem73 --version
```

The `modem73` binary lands in `~/.local/bin/` (pipx) or
`/usr/local/bin/` (system pip). The launcher scripts reference
`/usr/bin/modem73`; if you pipx-installed, symlink:

```bash
sudo ln -sf ~/.local/bin/modem73 /usr/bin/modem73
```

## Config

modem73 reads `~/.config/modem73/settings` in **TUI mode** (created
the first time you save the Config menu). In **headless mode**, the
launcher passes `--config ~/.config/modem73/settings` explicitly to
load the full file (see "Headless gotcha" below).

### Minimal config (KISS-over-Reticulum)

```ini
# Network
port=8002
control_port=8073
bind_address=0.0.0.0
control_bind_address=127.0.0.1

# Station
callsign=KJ5FQT

# Audio (set to 0 for "discard all samples" stub; works on any hardware)
audio_input=0
audio_output=0

# PTT (use rigctld for CAT-driven PTT; no FTDI cable required)
ptt_type=2     # 0=dummy, 1=COM, 2=rigctld, 3=VOX, 4=CM108 GPIO
vox_tone_freq=1200
vox_lead_ms=550
vox_tail_ms=500

# Modulation (defaults work; tune for your channel)
modulation=1       # 1=MFSK-16 (default, robust)
robust_mode=3
csma_enabled=1
carrier_threshold_db=-30.0
tx_drive=1.00
```

### Headless gotcha (discovered 2026-09-04)

`modem73 --headless` WITHOUT `--config` only loads a subset of
settings (audio, com, callsign, control-related). The `port=` and
`bind_address=` lines are silently ignored. Effect: modem73 binds to
its **binary default port 8001** even when the settings file says
8002.

Fix: always pass `--config` explicitly in headless invocations:

```bash
modem73 --headless --config /home/pi/.config/modem73/settings
```

The launcher's `start_modem73_loopback.sh` already does this.

## Reticulum interface wiring

Add a `[[Modem73]]` block to `/home/pi/.reticulum/config`:

```ini
[[Modem73]]
type = TCPClientInterface
target_host = 127.0.0.1
target_port = 8002
enabled = false   # flipped to true via the launcher's Start button
```

The `enabled` flag toggles whether rnsd actually carries traffic
over this interface. Flipping it requires `systemctl restart
reticulumhf-rnsd.service` (the launcher script does this).

### Why `enabled = false` by default

modem73 is on-demand (like freedvtnc2), not always-on. Operators
click Start in the launcher to bring the Reticulum interface up;
Stop removes it. The toggle is idempotent — clicking Start when
already enabled is a no-op (the script does a state check first).

## Launcher integration

The shared launcher (`/home/pi/shared_launcher/`) ships with three
modem73-related rows:

### Modem73 Config TUI (interactive)

- Opens an lxterminal on the shared desktop (`DISPLAY=:1`, visible
  in the noVNC tab) running `modem73` in TUI mode.
- TUI is the only way to **save the settings file** (Settings → Save
  in the Config menu). Headless mode does NOT write the file.
- Idempotent: clicking Start while a `modem73` TUI is already open
  exits early (no double-window).

### Modem73 Interface (headless, Reticulum-over-OFDM)

- Runs `modem73 --headless --config ~/.config/modem73/settings`
  as a detached subprocess (no systemd unit — modem73 has no service
  hook).
- Listener: KISS on 0.0.0.0:8002, control port on 127.0.0.1:8073.
- Toggle wiring:
  - **Start**: writes `enabled = true` to the `[[Modem73]]` Reticulum
    block, restarts rnsd. Pill turns green when rnsd confirms TCP
    connection.
  - **Stop**: writes `enabled = false`, restarts rnsd. Pill turns
    gray.
- **Do not run at the same time as the TUI row** — both spawn the
  same binary, settings are shared.

### Reset Audio Devices (audio reset)

- Sets `audio_input=0` and `audio_output=0` in the settings file
  (the ALSA "discard all samples" stub — always works on any
  hardware).
- Restarts the modem73 loopback subprocess.
- **Use when:** the audio device moved (e.g. digirig unplugged or
  switched USB ports) and modem73 fails to open the audio.
- The settings file edit is atomic (rename in place) so partial
  edits don't brick the modem.

## PTT integration

Modem73 has three PTT modes that work well with this fleet:

- **`ptt_type=2` (rigctld)**: recommended. Modem73 talks CAT to
  `rigctld` on `127.0.0.1:4532` and never touches the FTDI cable.
  No conflicts with `ardop_ptt_bridge.py` (which also uses
  rigctld — both share one process).
- **`ptt_type=0` (dummy)**: useful for testing without RF
  transmissions. The modem logs "PTT: Using dummy PTT" and never
  keys the radio. Safe to leave on 24/7.
- **`ptt_type=1` (COM)**: only if you have an FTDI cable dedicated
  to modem73. Conflicts with `ardop_ptt_bridge.py` on the same
  serial device.

The `ptt_type=2` mode is what the launcher's default settings use.

## Common tasks

### Save a new callsign / audio device / port

1. SSH to the box
2. Click **Modem73 Config TUI → Start** in the launcher
3. In the TUI: Config → set values → Save → Quit
4. Click **Modem73 Config TUI → Stop**
5. Click **Modem73 Interface → Stop**, then **Start** (to pick up
   the new settings)

### Recover from a bad audio device

1. Click **Reset Audio Devices** in the launcher (sets audio=0)
2. Modem73 loopback restarts with safe defaults
3. Click **Modem73 Config TUI → Start** if you want to pick a real
   device

### Toggle the Reticulum interface

- Click **Modem73 Interface → Start / Stop** in the launcher.
- The pill (`Modem73 interface`) reflects the actual state of
  `enabled = ...` in `/home/pi/.reticulum/config`. Green =
  enabled, gray = disabled.

## Troubleshooting

### "modem73 won't start: Audio open failed"

The configured audio device isn't present. Click **Reset Audio
Devices** to fall back to the always-works sink.

### "Modem73 interface pill is gray but modem73 is running"

The `[[Modem73]]` block in `/home/pi/.reticulum/config` is set to
`enabled = false`. Click **Modem73 Interface → Start** to flip it
and restart rnsd.

### "Port 8001 is already in use"

`freedvtnc2.service` is bound to 8001. This is the headless-mode
default for modem73 — you forgot to pass `--config`. Check
`/home/pi/shared_launcher/scripts/start_modem73_loopback.sh` has
`--config /home/pi/.config/modem73/settings` in the invocation.

### "modem73 starts from CLI but not from launcher"

The launcher passes `--config ~/.config/modem73/settings`. The CLI
without flags uses binary defaults. The settings file's `port=`
won't take effect unless `--config` is passed (see "Headless
gotcha" above).

## Files reference

| Path | What |
|---|---|
| `/home/pi/shared_launcher/scripts/start_modem73_tui.sh` | TUI launcher (uses lxterminal on DISPLAY=:1) |
| `/home/pi/shared_launcher/scripts/stop_modem73_tui.sh` | TUI killer (pkill by --title=modem73) |
| `/home/pi/shared_launcher/scripts/start_modem73_loopback.sh` | Headless modem73 launcher (with `--config`) |
| `/home/pi/shared_launcher/scripts/stop_modem73_loopback.sh` | Headless modem73 killer (pkill by --headless) |
| `/home/pi/shared_launcher/scripts/toggle_modem73_audio.sh` | Flips `enabled = true/false` in `[[Modem73]]` |
| `/home/pi/shared_launcher/scripts/reset_modem73_audio.sh` | Audio=0 reset + restart modem73 |
| `/home/pi/shared_launcher/scripts/check_modem73_in_reticulum.sh` | Reads `enabled` value (drives the pill) |
| `/home/pi/shared_launcher/scripts/parse_modem73_block.awk` | AWK parser for the `[[Modem73]]` block |
| `/home/pi/.config/modem73/settings` | Modem73's config (created via TUI Save) |

## Source-of-truth files

The launcher source lives in the `reticulumpi.git` public repo
(github: smeshT/reticulumpi). Per-box overrides (callsign, ZT ID,
specific audio device indexes) live in the private `g90digi.git`
repo under `etc-captures/<host>-<date>/` snapshots.
