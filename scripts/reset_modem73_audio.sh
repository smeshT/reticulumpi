#!/bin/bash
# reset_modem73_audio.sh — set audio_input=0 and audio_output=0 in
# ~/.config/modem73/settings, then restart the modem73 loopback
# subprocess so the new settings take effect.
#
# Why this exists (per operator 2026-09-04 16:36 MDT): modem73 refuses
# to start if the configured audio device index doesn't currently
# exist (e.g. USB digirig got unplugged, swapped to a different USB
# port which renumbered the ALSA cards). The launcher's Start button
# would silently fail. Setting both audio fields to 0 makes modem73
# use the system's "default" sink (PipeWire / PulseAudio always
# provide a default that just sends silence to nowhere), so the
# modem73 process boots cleanly and rnsd can carry traffic.
#
# What it changes:
#   * ~/.config/modem73/settings  ←  audio_input=N → 0
#                                     audio_output=N → 0
#   * modem73 loopback subprocess ← killed, then re-launched
#
# What it does NOT change:
#   * callsign, port, modulation, CSMA, tx_drive, etc.
#   * The Reticulum [[Modem73]] block (operator decides when to
#     enable that — the audio reset is independent).
#   * freedvtnc2 / meshchat / rnsd / rnsd-side Reticulum config.
#
# Box-independent: detects its own install dir via ${BASH_SOURCE[0]}
# so the same script body works on sbitx (my_launcher) and g90test
# (shared_launcher). Override with SCRIPTS_DIR env if you ever copy
# it somewhere exotic.
#
# Usage: reset_modem73_audio.sh  (no args)
# Exit codes:
#   0 = success
#   1 = settings file edit failed
#   2 = modem73 relaunch failed

set -u

CONFIG="/home/pi/.config/modem73/settings"
# Self-locating: the script's own directory holds start_modem73_loopback.sh
# and stop_modem73_loopback.sh. Falls back to env override for odd installs.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="${SCRIPTS_DIR:-$SCRIPT_DIR}"
START_SCRIPT="$SCRIPTS_DIR/start_modem73_loopback.sh"
STOP_SCRIPT="$SCRIPTS_DIR/stop_modem73_loopback.sh"

die() { echo "reset_modem73_audio: $*" >&2; exit "$2"; }

[ -f "$CONFIG" ]   || die "$CONFIG not found" 1
[ -x "$START_SCRIPT" ] || die "$START_SCRIPT not executable" 2
[ -x "$STOP_SCRIPT" ]  || die "$STOP_SCRIPT not executable" 2

# ---------- snapshot current audio values (for the log) ----------
before_input=$(grep -E '^audio_input=' "$CONFIG"  | head -1 | cut -d= -f2)
before_output=$(grep -E '^audio_output=' "$CONFIG" | head -1 | cut -d= -f2)
echo "before: audio_input=${before_input:-?} audio_output=${before_output:-?}"

# ---------- atomic config edit ----------
python3 - "$CONFIG" <<'PYEOF'
import sys, re, pathlib
p = pathlib.Path(sys.argv[1])
text = p.read_text()

# Replace audio_input=N → audio_input=0 (N=anything; 0 is fine).
new_text, n_in = re.subn(r'(?m)^audio_input=.*$', 'audio_input=0', text, count=1)
# Replace audio_output=N → audio_output=0.
new_text, n_out = re.subn(r'(?m)^audio_output=.*$', 'audio_output=0', new_text, count=1)

if n_in != 1 or n_out != 1:
    sys.exit(f'expected 1 audio_input and 1 audio_output line, got audio_input={n_in} audio_output={n_out}')

tmp = p.with_suffix('.settings.reset.tmp')
tmp.write_text(new_text)
tmp.replace(p)
print(f'config updated: audio_input=0, audio_output=0 (saved atomically)')
PYEOF
[ $? -eq 0 ] || die "config edit failed" 1

# ---------- restart modem73 loopback ----------
# The loopback script's pkill pattern is "modem73 --headless" so it
# only kills the loopback instance, not the operator's TUI mode.
"$STOP_SCRIPT"  || die "stop_modem73_loopback.sh failed" 2
sleep 1
"$START_SCRIPT" || die "start_modem73_loopback.sh failed" 2

echo "after:  audio_input=0 audio_output=0 (default sink — works on any hardware)"
echo "done: modem73 loopback restarted with default audio"
exit 0
