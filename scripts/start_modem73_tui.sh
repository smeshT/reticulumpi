#!/bin/bash
# start_modem73_tui.sh — open an lxterminal running modem73 in TUI mode
# on the g90test box's shared desktop (:1, visible in the noVNC tab).
#
# Pattern source: g90 box's freedv_tui.sh (clean lxterminal approach).
# NOT the sbitx freedvtnc2 TUI pattern (ttyd-shim + tmux + Conflicts=
# unit graph — that approach has known issues and the operator doesn't
# want to duplicate it).
#
# TUI mode = no --headless flag. modem73 in TUI mode renders an
# interactive OFDM terminal in the terminal window — the operator can
# type commands, watch signal lock, etc.
#
# IMPORTANT: we do NOT pass --device / --input-device / --callsign on
# the modem73 CLI. Those CLI args would override whatever the operator
# saved in the TUI config (persisted at ~/.config/modem73/settings).
# Letting modem73 read its settings file = persistent config across
# launcher restarts. Matches what happens when the operator launches
# modem73 from an SSH terminal directly. (Bug found 2026-09-04 15:15
# MDT: the old script passed -d plughw:... --input-device plughw:...
# --callsign, which clobbered saved settings on every launcher Start.)
#
# Conflict story (per operator 2026-09-04 13:05 MDT): modem73 in TUI
# mode opens an audio device directly; the modem73 Loopback instance
# (`start_modem73_loopback.sh`) uses plughw:Loopback so they
# don't directly share a device. BUT, both processes are running the
# same modem73 binary, and the operator reasoned they would collide in
# practice (e.g. sharing config files, sharing the ARDOP GPIO pins,
# etc.). We don't enforce a Conflicts= here — operator's responsibility
# to not run both at once. The Loopback instance is the production path
# for Reticulum-over-OFDM; this TUI is for ad-hoc operator inspection.
#
# Idempotent: if an lxterminal whose title is "modem73" is already
# open, this script is a no-op (matches on the title reliably, not
# on pgrep -f which self-matches the wrapper itself).

set -e

# The launcher systemd unit (my-launcher.service) inherits the systemd
# default environment, which does NOT include DISPLAY. We need
# DISPLAY=:1 to attach the lxterminal to the existing Xvfb :1
# desktop. We also need XDG_RUNTIME_DIR for the lxterminal to find
# its DBus session.
export DISPLAY=:1
export XDG_RUNTIME_DIR=/run/user/$(id -u)

# Idempotency check: look at each lxterminal's /proc/<pid>/cmdline
# and see if any of them were launched with --title=modem73. If so,
# focus it (best effort) and exit. We can't use pgrep -x lxterminal
# alone because that matches ANY lxterminal, including ones we don't
# own.
for p in $(pgrep -x lxterminal 2>/dev/null); do
    if cat /proc/$p/cmdline 2>/dev/null | tr '\0' ' ' | grep -q -- '--title=modem73'; then
        if command -v wmctrl >/dev/null 2>&1; then
            wmctrl -a "modem73" 2>/dev/null || true
        fi
        exit 0
    fi
done

# Open the terminal running modem73 in TUI mode. No --headless
# flag (that's the whole point of a TUI). No --device / --callsign
# either — let modem73 read its saved settings from
# ~/.config/modem73/settings so operator's TUI-config changes stick.
lxterminal --title="modem73" \
    -e bash -c "echo '=== modem73 TUI starting (reads ~/.config/modem73/settings) ==='; \
                 echo; \
                 echo 'If audio device or callsign are wrong, change them in the'; \
                 echo \"TUI's Config menu, save, then Quit and Restart.\"; \
                 echo; \
                 exec /usr/bin/modem73" \
    >/dev/null 2>&1 &

exit 0
