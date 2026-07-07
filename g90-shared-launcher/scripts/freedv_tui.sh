#!/bin/bash
# freedv_tui.sh — open an lxterminal running freedvtnc2 --cli in
# the g90 box's Xvfb :1 desktop (visible in the noVNC tab).
#
# This is the g90's analog of the sbitx box's ttyd-freedvtnc2
# sidecar, but simpler: no ttyd, no systemd unit, no tmux. The
# terminal is a real lxterminal on the existing desktop, and the
# user gets the full TNC terminal experience (mode, signal,
# connections, etc.) without any wrapper plumbing.
#
# Idempotent: if an lxterminal whose title is "freedvtnc2" is
# already open, this script is a no-op (matches on the title
# reliably, not on pgrep -f which self-matches the wrapper itself).
#
# No-radio handling: if the audio device configured for freedvtnc2
# isn't present (the G90 isn't plugged in, the audio card moved,
# etc.), we don't run freedvtnc2 at all — we open the terminal,
# print a clear explanation, and wait for the user to read it
# before closing. This is "non-fragile" by design: the failure mode
# is visible and informative, not a flash-and-vanish that the
# user has to chase through journalctl.
#
# Reads the same FREEDVTNC2_CMD the daemon uses, from
# /etc/reticulumhf/config.env, so the audio device index and
# other settings stay in sync with the daemon. Strips --no-cli
# (we want the TUI, not the headless daemon mode) and runs the
# resulting command inside the lxterminal.

set -e

# The launcher's systemd unit (g90-shared-launcher.service) inherits
# the systemd default environment, which does NOT include DISPLAY.
# We need DISPLAY=:1 to attach the lxterminal to the existing
# Xvfb :1 desktop. We also need XDG_RUNTIME_DIR for the lxterminal
# to find its DBus session. The other launcher scripts (e.g.
# start_patmenu.sh) set the same vars the same way.
export DISPLAY=:1
export XDG_RUNTIME_DIR=/run/user/$(id -u)

# Read FREEDVTNC2_CMD from the g90 image's config file. We only
# need the value, not the file's other lines.
CONFIG_ENV=/etc/reticulumhf/config.env
if [ ! -r "$CONFIG_ENV" ]; then
    # Print the error in a terminal so the user can see it.
    lxterminal --title="freedvtnc2 (no config)" \
        -e bash -c "echo 'ERROR: cannot read $CONFIG_ENV' >&2; \
                     echo 'The g90 setup wizard must run before this works.' >&2; \
                     read -p 'Press Enter to close...' _" \
        >/dev/null 2>&1 &
    exit 1
fi
# shellcheck disable=SC1090
source "$CONFIG_ENV"

if [ -z "${FREEDVTNC2_CMD:-}" ]; then
    lxterminal --title="freedvtnc2 (no FREEDVTNC2_CMD)" \
        -e bash -c "echo 'ERROR: FREEDVTNC2_CMD is not set in $CONFIG_ENV' >&2; \
                     read -p 'Press Enter to close...' _" \
        >/dev/null 2>&1 &
    exit 1
fi

# Idempotency: if our lxterminal is already open, focus it (best
# effort) and exit. We match on --title=freedvtnc2 exactly so we
# don't conflict with any other lxterminal the user might have
# open. We use wmctrl if available to raise the existing window;
# if not, we just exit.
#
# Implementation note: `pgrep -x lxterminal` returns 0 if ANY
# lxterminal is running, even ones we don't own. We need a
# positive test for "an lxterminal with our title is running"
# that returns 0 in that case and non-zero otherwise. We do this
# by checking each lxterminal's /proc/$pid/cmdline explicitly,
# returning 0 on the first match and skipping the rest.
ALREADY_RUNNING=0
for p in $(pgrep -x lxterminal 2>/dev/null); do
    if cat /proc/$p/cmdline 2>/dev/null | tr '\0' ' ' | grep -q -- '--title=freedvtnc2'; then
        ALREADY_RUNNING=1
        break
    fi
done
if [ "$ALREADY_RUNNING" = 1 ]; then
    if command -v wmctrl >/dev/null 2>&1; then
        wmctrl -a "freedvtnc2" 2>/dev/null || true
    fi
    exit 0
fi

# Extract the audio device index from FREEDVTNC2_CMD. The cmd
# looks like:
#   /home/pi/.local/bin/freedvtnc2 --no-cli --input-device 1 \
#     --output-device 1 --mode DATAC1 --rigctld-port 4532 ...
# We look for --input-device (and --output-device, should be the
# same number) and grab the next token.
INPUT_DEV=$(printf '%s\n' "$FREEDVTNC2_CMD" | grep -oE -- '--input-device[ =][0-9]+' | grep -oE '[0-9]+' | head -1)
OUTPUT_DEV=$(printf '%s\n' "$FREEDVTNC2_CMD" | grep -oE -- '--output-device[ =][0-9]+' | grep -oE '[0-9]+' | head -1)

# Pre-flight: is the audio device actually present? arecord -l
# prints lines like:
#   card 1: vc4hdmi0 [vc4-hdmi-0], device 0: MAI PCM i2s-hifi-0 ...
# We extract the card numbers and check our config against them.
MISSING=0
if [ -n "$INPUT_DEV" ]; then
    if ! arecord -l 2>/dev/null | grep -qE "^card ${INPUT_DEV}:"; then
        MISSING=1
    fi
fi
if [ -n "$OUTPUT_DEV" ] && [ "$MISSING" = 0 ]; then
    if ! aplay -l 2>/dev/null | grep -qE "^card ${OUTPUT_DEV}:"; then
        MISSING=1
    fi
fi

# Build the CLI command: same as FREEDVTNC2_CMD but with --no-cli
# stripped. We use a simple sed for the strip — the flag appears
# at most once and is always --no-cli (no value).
CLI_CMD=$(printf '%s\n' "$FREEDVTNC2_CMD" | sed -E 's/(^| )--no-cli( |$)/\1\2/g' | tr -s ' ')

if [ "$MISSING" = 1 ]; then
    # Open the terminal with a clear "no radio" message. Wait
    # for Enter so the user can read it before the window
    # closes. This is the non-fragile failure mode: visible,
    # informative, no flashing-and-vanishing.
    lxterminal --title="freedvtnc2 (no audio)" \
        -e bash -c "echo '=== FreeDV TUI: audio device not found ==='; \
                     echo; \
                     echo 'Configured audio devices (from $CONFIG_ENV):'; \
                     echo \"  --input-device  ${INPUT_DEV:-<unset>}\"; \
                     echo \"  --output-device ${OUTPUT_DEV:-<unset>}\"; \
                     echo; \
                     echo 'arecord -l output:'; \
                     arecord -l 2>&1 | sed 's/^/  /'; \
                     echo; \
                     echo 'aplay -l output:'; \
                     aplay -l 2>&1 | sed 's/^/  /'; \
                     echo; \
                     echo 'To fix:'; \
                     echo '  1. Plug in the G90 (USB audio + serial appear as new cards).'; \
                     echo '  2. If the device index changed, edit AUDIO_CARD in'; \
                     echo \"     $CONFIG_ENV (current value: \${AUDIO_CARD:-<unset>}).\"; \
                     echo '  3. Re-run this terminal.'; \
                     echo; \
                     read -p 'Press Enter to close...' _" \
        >/dev/null 2>&1 &
    exit 0
fi

# Audio device is present. Open the terminal running the CLI.
# We do this last so the existing-window check above sees the
# previous session (if any) and refuses to spawn a duplicate.
lxterminal --title="freedvtnc2" \
    -e bash -c "echo '=== FreeDV TUI starting ==='; \
                 echo; \
                 echo 'Command: $CLI_CMD'; \
                 echo 'Devices: input=$INPUT_DEV output=$OUTPUT_DEV'; \
                 echo; \
                 exec $CLI_CMD" \
    >/dev/null 2>&1 &

exit 0
