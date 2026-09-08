#!/bin/bash
# stop_pavucontrol.sh — close the running pavucontrol process.
#
# Pattern source: the original /home/jack/g90-launcher/scripts/stop_pavucontrol.sh
# used the sbitx helper `_lib_stop.sh::stop_proc_tree` which is not
# available on the g90digi image. Rewritten 2026-09-08 to use plain
# `pkill -x` (exact-name match) which is portable across both images.
#
# No DISPLAY=:1 needed: pkill doesn't talk to the X server, it just
# sends SIGTERM to the process. PulseAudio handles the sink cleanup
# when its client exits.

set -e

if ! command -v pkill >/dev/null 2>&1; then
    echo "stop_pavucontrol: pkill not found on PATH" >&2
    exit 127
fi

# `pkill -x` matches the exact binary name, not the command line.
# Returns 0 (success) if at least one process matched and was signaled,
# 1 if no process matched. Both are acceptable exit states here.
if pkill -x pavucontrol 2>/dev/null; then
    echo "pavucontrol stopped"
    exit 0
else
    echo "pavucontrol was not running"
    exit 0
fi
