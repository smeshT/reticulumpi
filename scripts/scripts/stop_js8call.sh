#!/bin/bash
# stop_js8call.sh — kill js8call parent and /usr/bin/js8 child.
#
# Qt apps ignore SIGTERM. _lib_stop.sh's stop_proc_tree sends SIGTERM,
# waits, then escalates to SIGKILL if the process is still alive. That
# matches the sbitx launcher hardening (2026-06-23).
LIB=/home/pi/shared_launcher/scripts/_lib_stop.sh
# shellcheck disable=SC1091
source "$LIB"
fail=0
stop_proc_tree "^(/usr/bin/js8call|js8call)$" || fail=1
stop_proc_tree "/usr/bin/js8 -s JS8Call"      || fail=1
[ "$fail" -eq 0 ] && echo "js8call stopped" || echo "js8call stop had errors"
exit $fail
