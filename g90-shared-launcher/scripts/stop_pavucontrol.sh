#!/bin/bash
# stop_pavucontrol.sh — kill pavucontrol.
LIB=/home/pi/shared_launcher/scripts/_lib_stop.sh
# shellcheck disable=SC1091
source "$LIB"
fail=0
stop_proc_tree "^(/usr/bin/pavucontrol|pavucontrol)$" || fail=1
[ "$fail" -eq 0 ] && echo "pavucontrol stopped" || echo "pavucontrol stop had errors"
exit $fail
