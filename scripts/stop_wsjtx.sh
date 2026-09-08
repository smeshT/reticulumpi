#!/bin/bash
# stop_wsjtx.sh — kill wsjtx.
LIB=/home/pi/shared_launcher/scripts/_lib_stop.sh
# shellcheck disable=SC1091
source "$LIB"
fail=0
stop_proc_tree "^(/usr/bin/wsjtx|wsjtx|wsjtxapp)$" || fail=1
[ "$fail" -eq 0 ] && echo "wsjtx stopped" || echo "wsjtx stop had errors"
exit $fail
