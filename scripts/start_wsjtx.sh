#!/bin/bash
# start_wsjtx.sh — start wsjtx on the existing Xvfb :1 desktop.
#
# See start_js8call.sh for the desktop/audio design notes.

set -e

if pgrep -x wsjtx >/dev/null 2>&1 || pgrep -f '^/usr/bin/wsjtx$' >/dev/null 2>&1; then
    exit 0
fi

export DISPLAY=:1
export XDG_RUNTIME_DIR=/run/user/$(id -u)

nohup /usr/bin/wsjtx >/tmp/shared_launcher_wsjtx.log 2>&1 &
exit 0
