#!/bin/bash
# stop_modem73_tui.sh — close the modem73 TUI lxterminal opened by
# start_modem73_tui.sh.
#
# Pattern source: g90's stop_freedv_tui.sh — kill by --title match so
# we don't touch other lxterminals the user has open on the desktop.

# || true so a no-match exit does not trip the Flask route into HTTP 500.
pkill -f "lxterminal.*--title=modem73" 2>/dev/null || true
sleep 1
exit 0
