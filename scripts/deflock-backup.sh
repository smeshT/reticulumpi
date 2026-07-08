#!/bin/bash
# =============================================================================
# deflock-backup.sh — Mirror workspace/deflock/ to USB with 7-day safety net
# =============================================================================
# Strategy: option 2 (mirror + safety net)
#   - Mirror workspace/deflock/ to /media/pi/USB20FD/Main/Projects/deflock/
#   - On overwrite/delete, the old version goes to:
#     /media/pi/USB20FD/Main/Backups/deflock-YYYYMMDD/
#   - Auto-prune backups older than 7 days
#
# Idempotent — safe to run as often as you like.
# Safe to run while files are being modified — rsync handles partial writes.
#
# Cron setup (see install-cron.sh):
#   3am daily
# =============================================================================

set -euo pipefail

# ---- config ------------------------------------------------------------------
SRC="/home/pi/.openclaw/workspace/deflock/"
DST="/media/pi/USB20FD/Main/Projects/deflock/"
BACKUP_ROOT="/media/pi/USB20FD/Main/Backups"
BACKUP_NAME="deflock-$(date +%Y%m%d)"
BACKUP_DIR="${BACKUP_ROOT}/${BACKUP_NAME}"
RETENTION_DAYS=7
LOG="/home/pi/.openclaw/logs/deflock-backup.log"

# ---- preflight ---------------------------------------------------------------
mkdir -p "$(dirname "$LOG")" "$BACKUP_ROOT" "$DST"

# Sanity: source must exist, USB must be mounted
if [ ! -d "$SRC" ]; then
  echo "[$(date -Iseconds)] ERROR: source not found: $SRC" | tee -a "$LOG"
  exit 1
fi
if ! mountpoint -q /media/pi/USB20FD 2>/dev/null; then
  echo "[$(date -Iseconds)] ERROR: USB not mounted at /media/pi/USB20FD" | tee -a "$LOG"
  exit 1
fi

echo "[$(date -Iseconds)] starting backup: $SRC -> $DST" | tee -a "$LOG"

# ---- pull latest from origin ------------------------------------------------
# Jack edits from his laptop via VS Code + GitHub, so the Pi's local copy
# may be behind. Pull before mirroring so the USB backup reflects the
# real published state, not a stale local checkout.
# --ff-only refuses to do anything non-trivial (no merge commits) so a
# half-finished local edit can't get clobbered silently.
cd "$SRC" || { echo "[$(date -Iseconds)] ERROR: cd $SRC failed" | tee -a "$LOG"; exit 1; }
git pull --ff-only 2>&1 | tee -a "$LOG" || {
  echo "[$(date -Iseconds)] WARN: git pull failed (ff-only); continuing with local state" | tee -a "$LOG"
}
cd - >/dev/null 2>&1 || true

# ---- mirror with safety net --------------------------------------------------
# --delete         remove files from DST that don't exist in SRC
# --backup         move replaced/deleted files to --backup-dir
#                  (newer-changed files go in place; only replaced files move)
# --backup-dir    destination for the "replaced" files
#                  (rsync creates this dir only if something was replaced)
# -a               archive mode (recursive, perms, links, times, etc.)
#
# Note: rsync's --backup-dir only captures files that are being
# replaced or deleted, not files that are being created fresh in DST.
# That's exactly what we want for the safety net.

rsync -a --delete \
      --backup --backup-dir="$BACKUP_DIR" \
      "$SRC" "$DST" 2>&1 | tee -a "$LOG" || {
  echo "[$(date -Iseconds)] ERROR: rsync failed" | tee -a "$LOG"
  exit 1
}

# ---- prune old backups -------------------------------------------------------
# Remove dated backup directories older than RETENTION_DAYS.
# Only removes dirs matching deflock-YYYYMMDD pattern (won't touch other stuff).

PRUNED=$(find "$BACKUP_ROOT" -maxdepth 1 -type d -name "deflock-20*" \
         -mtime +${RETENTION_DAYS} -print -exec rm -rf {} + 2>/dev/null || true)

if [ -n "$PRUNED" ]; then
  echo "[$(date -Iseconds)] pruned old backups:" | tee -a "$LOG"
  echo "$PRUNED" | tee -a "$LOG"
fi

echo "[$(date -Iseconds)] backup complete" | tee -a "$LOG"
