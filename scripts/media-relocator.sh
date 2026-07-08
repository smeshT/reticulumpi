#!/usr/bin/env bash
# media-relocator.sh — Move large Telegram/media files out of OpenClaw's
# inbound directory to the USB dropbox inbox, replacing them with a small
# stub the model can see but won't bloat context with.
#
# WHY: PDF / image / video files dropped via Telegram land in
#   ~/.openclaw/media/inbound/  and get attached to the agent turn. Large
#   files eat context window. We move them to the USB dropbox inbox and
#   leave a stub behind.
#
# BEHAVIOR:
#   - Watches ~/.openclaw/media/inbound/ via inotifywait (close_write).
#   - Files > THRESHOLD_BYTES (default 1 MB) get moved to:
#       /media/pi/USB20FD/Working/inbox/relocated/<original-name>
#     A stub file of the same name is left in inbound/ with a brief note.
#   - Files <= THRESHOLD_BYTES pass through untouched.
#   - Every action is appended to LOG_FILE.
#   - Moves are atomic (mv). The original path stays valid (now a stub).
#   - Idempotent: re-running is safe. Existing stubs are left alone.
#
# RUN AS: user 'pi', not root. No sudo needed.
#
# CONTROL:
#   /home/pi/.openclaw/workspace/scripts/media-relocator.sh start   # daemonize
#   .../media-relocator.sh stop    # kill the running instance
#   .../media-relocator.sh status  # show PID + log tail
#   .../media-relocator.sh run     # run in foreground (debug)
#   .../media-relocator.sh once    # scan existing files (catch-up), no watch

set -euo pipefail

WATCH_DIR="$HOME/.openclaw/media/inbound"
INBOX_DIR="/media/pi/USB20FD/Working/inbox/relocated"
STUB_SUFFIX=".relocated.txt"
LOG_FILE="$HOME/.openclaw/logs/relocator.log"
PID_FILE="/tmp/media-relocator.pid"
THRESHOLD_BYTES="${RELOCATOR_THRESHOLD_BYTES:-1048576}"   # 1 MB

mkdir -p "$INBOX_DIR" "$(dirname "$LOG_FILE")"

#--- helpers ------------------------------------------------------------------

log() {
    local ts
    ts="$(date -Iseconds)"
    printf "%s [%s] %s\n" "$ts" "${1:-info}" "${2:-}" >> "$LOG_FILE"
}

is_relocated_stub() {
    # A stub starts with our magic marker. Heuristic, not a hard rule —
    # the model can read it and tell.
    local f="$1"
    [[ -f "$f" ]] || return 1
    head -c 32 "$f" 2>/dev/null | grep -q "MEDIA-RELOCATED-STUB"
}

build_stub() {
    # Generates the replacement content for the moved file.
    # Body explains where the real file went and what to do.
    local original_name="$1"
    local new_path="$2"
    local size_bytes="$3"
    cat <<EOF
MEDIA-RELOCATED-STUB v1
This file was moved out of OpenClaw's inbound directory to keep the agent
context window small. The original payload lives at:

    ${new_path}

Original name: ${original_name}
Original size: ${size_bytes} bytes ($(( size_bytes / 1024 )) KB)
Moved at:      $(date -Iseconds)
Relocator:     media-relocator.sh (threshold ${THRESHOLD_BYTES} bytes)

To read the original, use the read tool on the new path above. You can also
ask Slate to "open the file at <new_path>" or "summarise the PDF in inbox/".
Do NOT try to read this stub as if it were the original — it isn't.
EOF
}

relocate_one() {
    local f="$1"
    # Skip if not a regular file, or already a stub, or a directory.
    [[ -f "$f" ]] || return 0
    is_relocated_stub "$f" && {
        log "debug" "skip stub: $f"
        return 0
    }
    local size
    size=$(stat -c %s "$f" 2>/dev/null || echo 0)
    (( size > THRESHOLD_BYTES )) || {
        log "debug" "skip small (${size}B): $f"
        return 0
    }
    # Build a non-colliding destination. Same name, but if a relocated
    # file with that name already exists, suffix with -N.
    local name
    name=$(basename "$f")
    local dest="$INBOX_DIR/$name"
    if [[ -e "$dest" ]]; then
        local i=1
        while [[ -e "${dest%.???}-${i}${name##*.}" ]] && (( i < 999 )); do
            ((i++))
        done
        # Simpler: append -N before the extension.
        local base="${name%.*}"
        local ext=""
        [[ "$name" == *.* ]] && ext=".${name##*.}"
        dest="${INBOX_DIR}/${base}-${i}${ext}"
    fi
    # Move the original to the USB.
    if mv "$f" "$dest" 2>>"$LOG_FILE"; then
        # Build a stub at the original path so the model still has a
        # file at the location it was told about.
        build_stub "$name" "$dest" "$size" > "$f"
        chmod 0644 "$f"
        log "info" "relocated: $f ($size bytes) -> $dest"
    else
        log "error" "mv failed: $f -> $dest"
        return 1
    fi
}

scan_existing() {
    # Catch-up pass: handle any files already in the dir when we start.
    log "info" "scan_existing starting (threshold=${THRESHOLD_BYTES}B)"
    local count=0
    while IFS= read -r -d '' f; do
        if (( $(stat -c %s "$f" 2>/dev/null || echo 0) > THRESHOLD_BYTES )); then
            if ! is_relocated_stub "$f"; then
                relocate_one "$f" && ((count++)) || true
            fi
        fi
    done < <(find "$WATCH_DIR" -maxdepth 1 -type f -print0 2>/dev/null)
    log "info" "scan_existing done ($count relocated)"
}

watch_loop() {
    log "info" "watcher starting on $WATCH_DIR"
    # inotifywait runs continuously, prints one event per line.
    inotifywait -m -e close_write -e moved_to --format '%w%f' "$WATCH_DIR" 2>>"$LOG_FILE" \
        | while IFS= read -r path; do
            # Give the file a moment to finish writing; large downloads
            # sometimes emit close_write before bytes are fully flushed
            # on slow SD cards.
            sleep 0.2
            [[ -f "$path" ]] || continue
            relocate_one "$path" || true
        done
}

#--- command dispatch ---------------------------------------------------------

cmd="${1:-status}"

case "$cmd" in
    start)
        if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "already running (pid $(cat "$PID_FILE"))"
            exit 0
        fi
        scan_existing
        nohup "$0" run > /dev/null 2>&1 &
        echo $! > "$PID_FILE"
        sleep 0.5
        if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "started (pid $(cat "$PID_FILE"), log: $LOG_FILE)"
        else
            echo "failed to start; check $LOG_FILE"
            exit 1
        fi
        ;;
    stop)
        if [[ -f "$PID_FILE" ]]; then
            local pid
            pid=$(cat "$PID_FILE")
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid"
                rm -f "$PID_FILE"
                echo "stopped (pid $pid)"
            else
                rm -f "$PID_FILE"
                echo "stale pid file removed"
            fi
        else
            echo "not running"
        fi
        ;;
    status)
        if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "running (pid $(cat "$PID_FILE"))"
        else
            echo "not running"
        fi
        echo "--- last 5 log lines ---"
        tail -5 "$LOG_FILE" 2>/dev/null || echo "(no log yet)"
        ;;
    run)
        # Foreground watcher (called by start via nohup)
        rm -f "$PID_FILE"
        echo $$ > "$PID_FILE"
        trap 'rm -f "$PID_FILE"; log "info" "watcher stopping"; exit 0' INT TERM
        watch_loop
        ;;
    once)
        scan_existing
        echo "scan complete; check $LOG_FILE"
        ;;
    *)
        echo "usage: $0 {start|stop|status|run|once}" >&2
        exit 2
        ;;
esac
