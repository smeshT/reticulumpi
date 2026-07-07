#!/bin/bash
# start_fldigi.sh — start fldigi on the existing Xvfb :1 desktop.
#
# See start_js8call.sh for the desktop/audio design notes.

set -e

if pgrep -x fldigi >/dev/null 2>&1 || pgrep -f '^/usr/bin/fldigi$' >/dev/null 2>&1; then
    exit 0
fi

export DISPLAY=:1
export XDG_RUNTIME_DIR=/run/user/$(id -u)

nohup /usr/bin/fldigi >/tmp/shared_launcher_fldigi.log 2>&1 &
exit 0
