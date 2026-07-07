#!/bin/bash
# start_patmenu.sh — start the patmenu2 yad menu on Xvfb :1.
#
# The yad menu itself contains a "Start/Stop Modem" button that
# launches piardopc + piARDOP_GUI. We only put the yad menu on the
# desktop; the user clicks the modem button when they want the
# modem up.
#
# The g90 box has patmenu2 source at /home/pi/patmenu2/patmenu, plus
# the pat Winlink client (apt: pat 0.13.1, binary at
# /usr/bin/pat-winlink, with a 'pat' symlink at
# /home/pi/.local/bin/pat for pipx discovery). The yad menu calls
# `pat version` (line 16) and `pat` for ARDOP setup; without a
# correct PATH, those calls fail with "pat: command not found".
#
# The launcher's systemd unit (g90-shared-launcher.service) inherits
# the systemd default PATH which does NOT include
# /home/pi/.local/bin. We extend it here so the yad menu finds pat
# and any other pipx-managed binary.
#
# Idempotent: if a yad process from the patmenu2 source is already
# running, this script is a no-op. We use a for loop over pgrep
# output, NOT a `pgrep | while read` pipe — the pipe form always
# returns 0 on the if-condition (an empty pgrep -> empty while ->
# pipe closed with status 0) which makes the script always exit
# without doing anything. The for loop is the correct form.

set -e

ALREADY_RUNNING=0
for p in $(pgrep -x yad 2>/dev/null); do
    if cat /proc/$p/cmdline 2>/dev/null | tr '\0' ' ' | grep -q 'patmenu2/pmlogo.png'; then
        ALREADY_RUNNING=1
        break
    fi
done
if [ "$ALREADY_RUNNING" = 1 ]; then
    # Best-effort focus the existing window; wmctrl may not be
    # installed and that's fine.
    if command -v wmctrl >/dev/null 2>&1; then
        wmctrl -a "Pat Menu" 2>/dev/null || true
    fi
    exit 0
fi

export DISPLAY=:1
export XDG_RUNTIME_DIR=/run/user/$(id -u)
# Prepend /home/pi/.local/bin so pipx-managed binaries (notably
# 'pat' -> /usr/bin/pat-winlink) are reachable. Keep the original
# PATH after so system tools still work.
export PATH=/home/pi/.local/bin:$PATH

nohup /home/pi/patmenu2/./patmenu \
    >/tmp/shared_launcher_patmenu.log 2>&1 &

exit 0
