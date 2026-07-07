#!/bin/bash
# _lib_stop.sh — hardened stop helpers for sbitx app launcher scripts
# Source this file: source /home/pi/sbitx/web/scripts/_lib_stop.sh
#
# Fixes over the previous stop_*.sh scripts:
#   - Uses SIGKILL after a SIGTERM grace period (Qt apps ignore SIGTERM)
#   - Verifies PIDs are alive before killing (silently no-opd kills were the
#     main bug: stale PID file => kill returns 0 => script reports "stopped"
#     => process still running)
#   - Verifies processes actually died after killing; escalates if needed
#   - Cleans up orphaned PID files on stale detection
#   - Catches app children (e.g. /usr/bin/js8 binary spawned by js8call)
#   - Supports EXCLUDE_PIDS env var so callers can protect their own
#     process tree from being killed (e.g. stop_desktop.sh must not kill the
#     launcher desktop that runs the very webserver that called it)
#
# Public functions:
#   stop_pidfile <pidfile> [label]      kill the PID in <pidfile>, remove file
#   stop_pid <pid> [label]              kill a specific PID
#   stop_proc <pattern> [signal]        kill all processes matching pattern
#                                       via pgrep -f (SIGKILL default)
#   stop_proc_tree <pattern> [signal]   like stop_proc but kills children too
#   verify_dead <pidfile> [label]       post-kill verification
#
# Behavior on success: prints "stopped <label>"
# Behavior on failure: prints "FAILED to stop <label> (pid=X)" and returns 1.
# Caller should aggregate exit codes; we do not exit early because the caller
# may want to attempt other stops even if one failed.

# Read EXCLUDE_PIDS from env; populate _EXCLUDE_PIDS array of PIDs to skip
declare -ga _EXCLUDE_PIDS=()
if [ -n "$STOP_EXCLUDE_PIDS" ]; then
    # comma or whitespace separated
    IFS="," read -ra _parts <<< "$STOP_EXCLUDE_PIDS"
    for p in "${_parts[@]}"; do
        p="$(echo "$p" | tr -d "[:space:]")"
        [ -n "$p" ] && _EXCLUDE_PIDS+=("$p")
    done
fi
# Always exclude self and parent shell to avoid killing the script that
# is running this library. $BASHPID is this subshell, $$ is the script shell.
[ -n "$BASHPID" ] && _EXCLUDE_PIDS+=("$BASHPID")
[ -n "$$" ] && _EXCLUDE_PIDS+=("$$")

# Format _EXCLUDE_PIDS for use in pgrep filters
_excluded_pgrep_filter() {
    # pgrep does not natively exclude PIDs. We will post-filter.
    echo ""
}

_is_excluded() {
    local pid="$1"
    for ep in "${_EXCLUDE_PIDS[@]}"; do
        [ "$pid" = "$ep" ] && return 0
    done
    return 1
}

_graceful_kill() {
    local pid="$1"
    local label="${2:-pid $pid}"
    [ -z "$pid" ] && return 0
    _is_excluded "$pid" && { echo "  (skipping excluded pid=$pid: $label)"; return 0; }
    kill -0 "$pid" 2>/dev/null || return 0
    kill "$pid" 2>/dev/null
    for _ in 1 2 3 4 5; do
        sleep 1
        kill -0 "$pid" 2>/dev/null || return 0
    done
    kill -9 "$pid" 2>/dev/null
    sleep 0.5
    if kill -0 "$pid" 2>/dev/null; then
        echo "FAILED to kill $label (pid=$pid)" >&2
        return 1
    fi
}

stop_pid() {
    local pid="$1"
    local label="${2:-pid $pid}"
    [ -z "$pid" ] && return 0
    _is_excluded "$pid" && { echo "$label is excluded (pid=$pid)"; return 0; }
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "$label was not running"
        return 0
    fi
    echo "Stopping $label (pid=$pid)"
    if _graceful_kill "$pid" "$label"; then
        echo "stopped $label"
        return 0
    fi
    return 1
}

stop_pidfile() {
    local pf="$1"
    local label="${2:-$pf}"
    [ -f "$pf" ] || return 0
    local pid
    pid="$(cat "$pf" 2>/dev/null | tr -d "[:space:]")"
    if [ -z "$pid" ]; then
        echo "Removing empty $label pid file: $pf"
        rm -f "$pf"
        return 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "Removing stale $label pid file (pid=$pid not alive): $pf"
        rm -f "$pf"
        return 0
    fi
    stop_pid "$pid" "$label" && rm -f "$pf"
}

# Kill all processes whose command line matches a pattern.
# Excludes PIDs listed in _EXCLUDE_PIDS.
stop_proc() {
    local pattern="$1"
    local sig="${2:-9}"
    [ -z "$pattern" ] && return 0
    local pids
    pids="$(pgrep -f "$pattern" 2>/dev/null | tr "\n" " ")"
    # Filter out excluded PIDs
    local filtered=""
    for p in $pids; do
        if _is_excluded "$p"; then
            echo "  (skipping excluded pid=$p matching $pattern)"
        else
            filtered="$filtered $p"
        fi
    done
    pids="$filtered"
    if [ -z "$pids" ]; then
        return 0
    fi
    echo "Killing processes matching $pattern (pids:$pids, sig=$sig)"
    if [ "$sig" = "9" ]; then
        for p in $pids; do kill "$p" 2>/dev/null || true; done
        sleep 2
        local remaining
        remaining=""
        for p in $(pgrep -f "$pattern" 2>/dev/null); do
            _is_excluded "$p" && continue
            remaining="$remaining $p"
        done
        if [ -n "$remaining" ]; then
            echo "  escalating to SIGKILL:$remaining"
            for p in $remaining; do kill -9 "$p" 2>/dev/null || true; done
            sleep 0.5
        fi
    else
        for p in $pids; do kill -$sig "$p" 2>/dev/null || true; done
    fi
    local still=""
    for p in $(pgrep -f "$pattern" 2>/dev/null); do
        _is_excluded "$p" && continue
        still="$still $p"
    done
    if [ -n "$still" ]; then
        echo "FAILED to kill $pattern (still alive:$still)" >&2
        return 1
    fi
    return 0
}

stop_proc_tree() {
    local pattern="$1"
    [ -z "$pattern" ] && return 0
    local pids
    pids="$(pgrep -f "$pattern" 2>/dev/null)"
    [ -z "$pids" ] && return 0
    for pid in $pids; do
        _is_excluded "$pid" && continue
        local children
        children="$(pgrep -P "$pid" 2>/dev/null)"
        for c in $children; do
            if ! _is_excluded "$c"; then
                echo "Killing child of $pattern: $c"
                _graceful_kill "$c" "child $c" || true
            fi
        done
    done
    stop_proc "$pattern"
}

verify_dead() {
    local pf="$1"
    local label="${2:-pid file $pf}"
    if [ ! -f "$pf" ]; then
        return 0
    fi
    local pid
    pid="$(cat "$pf" 2>/dev/null | tr -d "[:space:]")"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo "FAILED: $label still alive (pid=$pid)" >&2
        return 1
    fi
    return 0
}
