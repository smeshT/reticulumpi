#!/bin/bash
# start_js8call.sh — start js8call on the existing Xvfb :1 desktop.
#
# The g90 box's node-portal already brings up Xvfb :1, x11vnc on 5900,
# and websockify on 6080. We don't start a desktop here — we just
# point js8call at the existing :1.
#
# On the sbitx box, this script also ran `sudo systemctl stop
# freedvtnc2 && sudo systemctl stop rnsd` to free the audio device.
# On the g90 the equivalent services are freedvtnc2.service (already
# failed/inactive) and reticulumhf-rnsd.service (the Reticulum
# network daemon for the g90 image). We deliberately do NOT stop
# reticulumhf-rnsd here — that's the g90's actual Reticulum stack and
# the user expects it to stay up. If audio is held by freedvtnc2 in
# the future, this script will need revisiting.

set -e

# Sanity: refuse to start a second instance. pgrep -x matches the bare
# process name; pgrep -f '^/usr/bin/js8call$' matches the absolute-path
# invocation. Either is enough. Both avoid matching our own bash since
# neither pattern appears in the script's command line.
if pgrep -x js8call >/dev/null 2>&1 || pgrep -f '^/usr/bin/js8call$' >/dev/null 2>&1; then
    exit 0
fi

export DISPLAY=:1
export XDG_RUNTIME_DIR=/run/user/$(id -u)

nohup /usr/bin/js8call >/tmp/shared_launcher_js8call.log 2>&1 &
exit 0
