#!/usr/bin/env bash
# slate-rotate.sh — Optional auto-revoke timer.
#
# Schedules a one-shot cron job that calls slate-revoke.sh --yes after
# a given number of hours. Default: 24h. Pass an integer to override.
#
# Why: If you forget the sudoers drop-in is open, this auto-closes it.
# You (or I) can re-add the file from the template whenever needed.
#
# Usage:
#   /home/pi/.openclaw/workspace/scripts/slate-rotate.sh         # 24h
#   /home/pi/.openclaw/workspace/scripts/slate-rotate.sh 72      # 3 days
#   /home/pi/.openclaw/workspace/scripts/slate-rotate.sh --cancel

set -euo pipefail

REVOKE_SCRIPT="/home/pi/.openclaw/workspace/scripts/slate-revoke.sh"
CRON_TAG="slate-auto-revoke"

cancel() {
    crontab -l 2>/dev/null | grep -v "$CRON_TAG" | crontab - 2>/dev/null || true
    echo "[$(date -Iseconds)] Cancelled any pending $CRON_TAG cron entries."
    exit 0
}

case "${1:-}" in
    --cancel|-c) cancel ;;
esac

HOURS="${1:-24}"
if ! [[ "$HOURS" =~ ^[0-9]+$ ]] || [[ "$HOURS" -lt 1 ]]; then
    echo "Hours must be a positive integer. Got: $1"
    exit 1
fi

# Compute the absolute run time, in the host's local timezone.
RUN_AT=$(date -d "+${HOURS} hours" '+%M %H %d %m *')
RUN_HUMAN=$(date -d "+${HOURS} hours" '+%Y-%m-%d %H:%M:%S %Z')

# Append a tagged cron line. Idempotent: cancels existing tagged lines first.
( crontab -l 2>/dev/null | grep -v "$CRON_TAG" || true
  echo "$RUN_AT $REVOKE_SCRIPT --yes  # $CRON_TAG" ) | crontab -

echo "[$(date -Iseconds)] Scheduled auto-revoke in ${HOURS}h at $RUN_HUMAN"
echo "Cancel any time with: $0 --cancel"
