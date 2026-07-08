#!/bin/bash
# =============================================================================
# install-cron.sh — Install deflock-backup.sh as a nightly cron job
# =============================================================================
# Idempotent — re-running just updates the existing crontab entry.
# Run once: bash install-cron.sh
# =============================================================================

set -uo pipefail

SCRIPT="/home/pi/.openclaw/workspace/scripts/deflock-backup.sh"
CRON_TAG="# deflock-backup-managed"
CRON_LINE="0 3 * * * ${SCRIPT} ${CRON_TAG}"

# Make sure script is executable
chmod +x "$SCRIPT"

# Get current crontab (if any) and remove old managed entry.
# crontab -l exits 1 when no crontab exists; tolerate that.
CURRENT=$(crontab -l 2>/dev/null || true)
NEW=$(echo "$CURRENT" | grep -v "$CRON_TAG" || true)

# Add the new line
( echo "$NEW"; echo "$CRON_LINE" ) | crontab -

echo "Cron installed: $CRON_LINE"
echo "Verify with: crontab -l"
