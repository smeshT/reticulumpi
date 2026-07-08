#!/bin/bash
# stop_patmenu.sh — stop the patmenu2 yad menu.
#
# We only kill the yad menu here. Pat's "Start/Stop Modem" button
# (which spawns piardopc / piARDOP_GUI) is a separate concern: those
# are managed inside the yad menu (or by closing the lxterminal in
# the noVNC tab).
#
# Pattern: stop yad whose command line includes /home/pi/patmenu2/
# (the pmlogo.png path is present in EVERY dialog the yad menu
# shows, including the "Call sign not set" one and the main menu).
# This is more reliable than matching "--title=Pat Menu" because the
# initial dialog (the callsign check) has title=call-sign, not
# "Pat Menu", and we want to kill it too.
#
# Use _lib_stop.sh for the stop_proc helpers so we get the same
# exclude-pids safety (the script's own bash subshell) as the other
# stop scripts.

LIB=/home/pi/shared_launcher/scripts/_lib_stop.sh
# shellcheck disable=SC1091
source "$LIB"
fail=0
stop_proc "patmenu2/pmlogo.png" || fail=1
[ "$fail" -eq 0 ] && echo "patmenu stopped" || echo "patmenu stop had errors"
exit $fail
