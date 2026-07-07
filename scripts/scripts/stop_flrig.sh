#!/bin/bash
# stop_flrig.sh — kill flrig.
LIB=/home/pi/shared_launcher/scripts/_lib_stop.sh
# shellcheck disable=SC1091
source "$LIB"
fail=0
stop_proc_tree "^(/usr/bin/flrig|flrig)$" || fail=1
[ "$fail" -eq 0 ] && echo "flrig stopped" || echo "flrig stop had errors"
exit $fail
