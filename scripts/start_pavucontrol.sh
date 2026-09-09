#!/bin/bash
# start_pavucontrol.sh — open the PulseAudio Volume Control GUI on
# the g90 box's Xvfb :1 desktop (visible in the noVNC tab).
#
# This is the g90digi-image equivalent of the launcher's pre-2026-08
# pavucontrol launcher row. The original script (in
# /home/jack/g90-launcher/scripts/start_pavucontrol.sh on the dev Pi)
# was written for the g90 box when it still mirrored the sbitx layout
# (DISPLAY=:20, /home/pi/my_launcher/scripts/start_desktop.sh, the
# sbitx _lib_stop.sh helpers). It stopped working when the g90digi
# image diverged from the sbitx structure (2026-08-09 image overhaul).
#
# The fix is to follow the same pattern as freedv_tui.sh (which was
# rewritten 2026-09-04): explicit DISPLAY=:1, XDG_RUNTIME_DIR export,
# idempotency check via /proc/$pid/cmdline, and a clear error message
# if the dependency is missing. pavucontrol doesn't talk to the radio
# (it's a PulseAudio sink/source mixer) so no audio device check is
# needed.
#
# Idempotent: if pavucontrol is already running, this script is a
# no-op. We match on the binary name (pavucontrol) via `pgrep -x`
# which returns 0 if any process with that exact name is alive.
#
# Failure mode: if pavucontrol isn't installed, the launcher should
# see the exit 127 and (eventually) the route should return an error
# to the operator. Right now run_script() swallows the exit code
# silently — the operator sees the launcher page reload but no
# window. That's the same UX gap as freedvtnc2 before the xterm
# fix; documented in memory/2026-09-08-freedv-chat-fix.md.

set -e

# The launcher's systemd unit (g90-shared-launcher.service) inherits
# the systemd default environment, which does NOT include DISPLAY.
# We need DISPLAY=:1 to attach to the existing Xvfb :1 desktop.
export DISPLAY=:1
export XDG_RUNTIME_DIR=/run/user/$(id -u)

if ! command -v pavucontrol >/dev/null 2>&1; then
    echo "start_pavucontrol: pavucontrol not found on PATH. Install with:" >&2
    echo "  sudo apt-get install -y pavucontrol" >&2
    exit 127
fi

# Idempotency: if pavucontrol is already running, exit cleanly
# without launching a second instance. `pgrep -x` matches the exact
# binary name (not command line), so we don't false-match on a shell
# that happens to have "pavucontrol" in its arguments.
if pgrep -x pavucontrol >/dev/null 2>&1; then
    # Best-effort focus the existing window via wmctrl if available.
    command -v wmctrl >/dev/null 2>&1 && wmctrl -a "pavucontrol" 2>/dev/null || true
    exit 0
fi

# Launch detached so the launcher's subprocess.Popen() returns
# immediately. Without `&` the launcher route would block on
# pavucontrol's main loop. We use `nohup` (not just `&` + `disown`)
# so the child survives the SIGHUP that the kernel sends to all
# processes in the script's session when the script itself exits.
# (Found 2026-09-09 15:54 MDT: `disown` only removes the child
# from the shell's job table; it does NOT make the child immune
# to session-leader SIGHUP. The other working start_*.sh scripts
# already use nohup; this one was missed in that audit.)
#
# Pulseaudio must be running before pavucontrol starts or the
# GUI spins forever waiting for a connection that never comes.
# On a fresh build, pulseaudio is installed but neither the
# system service nor the user service is enabled (the system
# service isn't shipped by Debian; the user service requires
# loginctl enable-linger, which the bootstrap doesn't do). We
# start pulseaudio on demand here, which works whether or not
# the user service is enabled. pulseaudio in this mode runs
# as the pi user and listens on /run/user/1000/pulse/.
# Idempotent: if pulseaudio is already running, this exits
# immediately. Discovered 2026-09-09 16:15 MDT when the
# launcher's "Start pavucontrol" button spun forever on a
# freshly-flashed box.
if ! pgrep -x pulseaudio >/dev/null 2>&1; then
    nohup pulseaudio --exit-idle-time=-1 >/tmp/pavucontrol.log 2>&1 &
    # Brief sleep so pulseaudio has time to create the socket
    # before pavucontrol tries to connect.
    sleep 1
fi
nohup pavucontrol >/tmp/pavucontrol.log 2>&1 &
exit 0
