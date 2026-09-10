#!/bin/bash
# box-backup-flow.sh — pull a g90 box's config from m5boss, archive, prep restore.
#
# Standalone for boxes where the launcher can't be updated (g90f1r2).
# Run from m5boss (or any dev box with ssh to the g90).
#
# Usage:
#   bash box-backup-flow.sh g90f1r2        # capture
#   bash box-backup-flow.sh g90f1r2 --send g90digi
#                                         # capture + copy to g90digi
#
# This script:
#   1. ssh to <source>, runs capture-config.sh, pulls the tarball back
#   2. optionally scp's the tarball to <target> and runs restore-config.sh

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <source-host> [--send <target-host>]" >&2
    exit 1
fi

SRC="$1"
shift
SEND_TARGET=""
if [ "${1:-}" = "--send" ] && [ -n "${2:-}" ]; then
    SEND_TARGET="$2"
    shift 2
fi

# Sanity: can we ssh to source?
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$SRC" "echo connected" 2>/dev/null; then
    echo "ERROR: cannot ssh to $SRC" >&2
    echo "(use the operator's askpass wrapper if password auth is needed)" >&2
    exit 1
fi

# Push the capture script to source, run it, pull the tarball back
echo "=== pushing capture-config.sh to $SRC ==="
scp "$(dirname "$0")/capture-config.sh" "$SRC:/tmp/capture-config.sh"
echo
echo "=== running capture on $SRC ==="
ssh "$SRC" "bash /tmp/capture-config.sh /tmp"
echo
echo "=== pulling tarball back ==="
TARBALL=$(ssh "$SRC" "ls -1t /tmp/g90-configs-*.tar.gz 2>/dev/null | head -1")
if [ -z "$TARBALL" ]; then
    echo "ERROR: no tarball produced on $SRC" >&2
    exit 1
fi
echo "  tarball: $TARBALL"
LOCAL_TARBALL="./$(basename "$TARBALL")"
scp "$SRC:$TARBALL" "$LOCAL_TARBALL"
echo "  saved locally: $LOCAL_TARBALL"
echo

# Optionally push to target
if [ -n "$SEND_TARGET" ]; then
    echo "=== pushing to $SEND_TARGET ==="
    if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$SEND_TARGET" "echo connected" 2>/dev/null; then
        echo "ERROR: cannot ssh to $SEND_TARGET" >&2
        exit 1
    fi
    scp "$(dirname "$0")/restore-config.sh" "$SEND_TARGET:/tmp/restore-config.sh"
    scp "$LOCAL_TARBALL" "$SEND_TARGET:/tmp/"
    echo
    echo "On $SEND_TARGET, the operator can run:"
    echo "  ssh $SEND_TARGET"
    echo "  bash /tmp/restore-config.sh /tmp/$(basename "$TARBALL")        # preview only"
    echo "  bash /tmp/restore-config.sh /tmp/$(basename "$TARBALL") --apply # apply"
fi
