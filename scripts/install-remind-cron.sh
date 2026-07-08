#!/bin/bash
# =============================================================================
# install-remind-cron.sh — Wire deflock-remind-push.sh into cron
# =============================================================================
# Runs every 30 minutes during Jack's working hours (08:00-22:00 UK time).
# Outside those hours, no nag — you're not editing at 3am.
# =============================================================================

set -uo pipefail

SCRIPT="/home/pi/.openclaw/workspace/scripts/deflock-remind-push.sh"
CRON_TAG="# deflock-remind-managed"
# Every 30 min between 08:00 and 21:59, then one final at 22:30 to catch the
# late-evening forgetful edit. Quiet the rest of the night.
CRON_LINE="*/30 8-21 * * * ${SCRIPT} ${CRON_TAG}"
CRON_LINE2="30 22 * * * ${SCRIPT} ${CRON_TAG}"

chmod +x "$SCRIPT"

CURRENT=$(crontab -l 2>/dev/null || true)
NEW=$(echo "$CURRENT" | grep -v "$CRON_TAG" || true)

( echo "$NEW"; echo "$CRON_LINE"; echo "$CRON_LINE2" ) | crontab -

echo "Cron installed:"
echo "  $CRON_LINE"
echo "  $CRON_LINE2"
echo ""
echo "Verify with: crontab -l"
