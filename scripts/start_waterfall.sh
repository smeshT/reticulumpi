#!/bin/bash
# start_waterfall.sh — open a freeDV waterfall diagnostic terminal
# on the g90 box's Xvfb :1 desktop (visible in the noVNC tab).
#
# Mirrors start_pavucontrol.sh and freedv_tui.sh: idempotent
# (no-op if already running, matched by lxterminal --title),
# runs on DISPLAY=:1, log to /tmp.

set -e

export DISPLAY=:1
export XDG_RUNTIME_DIR=/run/user/$(id -u)

# Idempotency: if a freedv-waterfall lxterminal is already open,
# focus it and exit. We match on the exact --title so we don't
# conflict with any other lxterminal the user has open.
for p in $(pgrep -x lxterminal 2>/dev/null); do
    if cat /proc/$p/cmdline 2>/dev/null | tr '\0' ' ' \
            | grep -q -- '--title=freedv-waterfall'; then
        if command -v wmctrl >/dev/null 2>&1; then
            wmctrl -a "freedv-waterfall" 2>/dev/null || true
        fi
        exit 0
    fi
done

# Where the tool lives. The g90 image installs it under
# /home/pi/.local/bin so it's on PATH. The launcher's tests run
# on the nomadpi test sled, where the script lives next to this
# one in scripts/ — we add the launcher's scripts/ dir to PATH
# for that case.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HOME/.local/bin:$SCRIPT_DIR:$PATH"

# Pre-flight: arecord -l must show the configured input device.
# The default device is the "g90audio" dsnoop alias. If the G90
# isn't plugged in, the device will be absent and the Python
# tool will fail with an opaque error. Catch it here with a
# visible message — same non-fragile UX as freedv_tui.sh.
DEVICE="${FD_WATERFALL_DEVICE:-g90audio}"
if ! arecord -l 2>/dev/null | grep -qE '^card '; then
    lxterminal --title="freedv-waterfall (no audio)" \
        -e bash -c "echo '=== freeDV Waterfall: no audio devices found ==='; \
                     echo; \
                     echo 'arecord -l output:'; \
                     arecord -l 2>&1 | sed 's/^/  /'; \
                     echo; \
                     echo 'Plug in the G90 (USB audio + serial appear as new cards).'; \
                     echo 'Then re-run from the launcher.'; \
                     echo; \
                     read -p 'Press Enter to close...' _" \
        >/dev/null 2>&1 &
    exit 0
fi
# Also pre-flight the dsnoop alias specifically: arecord -l lists
# physical cards, but the g90audio dsnoop is a virtual device
# defined in /etc/asound.conf. If the alias is missing, the
# Python tool crashes with "Device or resource busy" or "No
# such device" depending on ALSA's mood. arecord -L lists
# aliases and should mention our dsnoop device.
if ! arecord -L 2>/dev/null | grep -qE "^${DEVICE}\b"; then
    lxterminal --title="freedv-waterfall (no dsnoop)" \
        -e bash -c "echo '=== freeDV Waterfall: dsnoop device \"$DEVICE\" not found ==='; \
                     echo; \
                     echo 'Expected: a dsnoop alias named \"$DEVICE\" in /etc/asound.conf'; \
                     echo '          that wraps the G90 USB audio card.'; \
                     echo; \
                     echo 'arecord -L output:'; \
                     arecord -L 2>&1 | sed 's/^/  /'; \
                     echo; \
                     echo 'Fix: define the g90audio dsnoop device in /etc/asound.conf.'; \
                     echo 'See memory/2026-07-09-waterfall-tool.md for the snippet.'; \
                     echo; \
                     read -p 'Press Enter to close...' _" \
        >/dev/null 2>&1 &
    exit 0
fi

# Run the Python tool. Pass the device explicitly so the user
# can override per-launch with FD_WATERFALL_DEVICE if needed.
# The tool runs curses; the lxterminal provides the TTY.
lxterminal --title="freedv-waterfall" \
    -e bash -c "exec freedv_waterfall.py --device '$DEVICE'" \
    >/tmp/shared_launcher_waterfall.log 2>&1 &

exit 0
