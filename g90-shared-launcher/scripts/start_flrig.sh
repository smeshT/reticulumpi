#!/bin/bash
# start_flrig.sh — start flrig on the existing Xvfb :1 desktop.
#
# FLrig is the rig-control GUI (talks to the radio over hamlib). On
# the g90 box, the radio is wired via USB serial and flrig connects
# via hamlib. The g90 already has rigctld.service (hamlib daemon)
# running on 4532 — flrig is the optional GUI on top.
#
# See start_js8call.sh for the desktop/audio design notes.

set -e

if pgrep -x flrig >/dev/null 2>&1 || pgrep -f '^/usr/bin/flrig$' >/dev/null 2>&1; then
    exit 0
fi

export DISPLAY=:1
export XDG_RUNTIME_DIR=/run/user/$(id -u)

nohup /usr/bin/flrig >/tmp/shared_launcher_flrig.log 2>&1 &
exit 0
