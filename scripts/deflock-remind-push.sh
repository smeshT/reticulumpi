#!/bin/bash
# =============================================================================
# deflock-remind-push.sh — Remind Jack about uncommitted/unpushed deflock changes
# =============================================================================
# Run periodically (cron or heartbeat). Detects:
#   1. Local uncommitted changes (git status dirty)
#   2. Local commits not yet pushed to origin (git status ahead)
# For each condition, posts a reminder to Telegram.
#
# Idempotent — safe to run as often as you like.
# Dedupes via /home/pi/.openclaw/state/deflock-remind.state
# =============================================================================

set -uo pipefail

REPO="/home/pi/.openclaw/workspace/deflock"
LOG="/home/pi/.openclaw/logs/deflock-remind.log"
STATE_DIR="/home/pi/.openclaw/state"
STATE_FILE="${STATE_DIR}/deflock-remind.state"
CHAT_ID="8704809525"
TELEGRAM_BIN="/usr/local/bin/telegram-notify"

mkdir -p "$(dirname "$LOG")" "$STATE_DIR"

log() { echo "[$(date -Iseconds)] $*" | tee -a "$LOG"; }

# Escape a multi-line message for safe use inside double quotes
escape_for_double_quotes() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\$/\\$/g; s/`/\\`/g'
}

# ---- preflight ---------------------------------------------------------------
if [ ! -d "$REPO/.git" ]; then
  log "ERROR: $REPO is not a git repo"
  exit 1
fi

cd "$REPO" || exit 1

# ---- gather state ------------------------------------------------------------
# Behind/ahead counts vs origin/main
AHEAD=$(git rev-list --count @{u}..HEAD 2>/dev/null || echo "?")
BEHIND=$(git rev-list --count HEAD..@{u} 2>/dev/null || echo "?")

# Dirty working tree (uncommitted or unstaged)
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  DIRTY=1
  DIRTY_LIST=$(git status --short 2>/dev/null | head -10)
  DIRTY_COUNT=$(git status --porcelain 2>/dev/null | wc -l)
else
  DIRTY=0
  DIRTY_LIST=""
  DIRTY_COUNT=0
fi

# Compose message
MSGS=""

if [ "$DIRTY" = "1" ]; then
  MSGS="${MSGS}⚠️ *Uncommitted changes in deflock/* (${DIRTY_COUNT} files):"
  MSGS="${MSGS}
\`\`\`
${DIRTY_LIST}
\`\`\`
Save your work: \`cd ~/.openclaw/workspace/deflock && git add -A && git commit -m '...' && git push\`
"
fi

if [ "$AHEAD" != "0" ] && [ "$AHEAD" != "?" ]; then
  MSGS="${MSGS}📤 *${AHEAD} commit(s) ahead of origin/main* — push to deploy:"
  MSGS="${MSGS}
\`cd ~/.openclaw/workspace/deflock && git push\`
"
fi

# Behind is a separate concern (someone else pushed); usually just Jack and me,
# so flag it but don't shout.
if [ "$BEHIND" != "0" ] && [ "$BEHIND" != "?" ]; then
  MSGS="${MSGS}🔄 *Behind origin/main by ${BEHIND} commit(s)* — pull before editing:"
  MSGS="${MSGS}
\`cd ~/.openclaw/workspace/deflock && git pull\`
"
fi

# ---- dedupe & send -----------------------------------------------------------
# Hash of message body; only resend if it changes (so the user doesn't get the
# same nag every 30 min).
MSG_HASH=$(printf "%s" "$MSGS" | md5sum | awk '{print $1}')
PREV_HASH=$(cat "$STATE_FILE" 2>/dev/null || echo "")

if [ -z "$MSGS" ]; then
  # All clean — clear the dedupe state so next time anything changes we fire
  rm -f "$STATE_FILE"
  log "clean — no reminder needed"
  exit 0
fi

if [ "$MSG_HASH" = "$PREV_HASH" ]; then
  log "no change since last reminder (hash $MSG_HASH), skipping"
  exit 0
fi

# Send via OpenClaw's internal messaging — uses the gateway token, no need
# for a separate Telegram bot. Falls back to plain curl if telegram-notify
# is not available.
send_telegram() {
  local text="$1"
  if [ -x "$TELEGRAM_BIN" ] || [ -f "$TELEGRAM_BIN" ]; then
    "$TELEGRAM_BIN" --chat "$CHAT_ID" --text "$text" 2>>"$LOG"
  else
    # Fallback: use the openclaw gateway to deliver.
    # Write the message to a temp file to avoid quoting issues with newlines,
    # markdown backticks, $, etc.
    local tmpf
    tmpf=$(mktemp)
    printf '%s' "$text" > "$tmpf"
    bash -c "source ~/.nvm/nvm.sh && nvm use 22 >/dev/null 2>&1 && openclaw message send --channel telegram --target $CHAT_ID --message \"\$(cat $tmpf)\"" 2>>"$LOG" || true
    rm -f "$tmpf"
  fi
}

send_telegram "$MSGS"
echo "$MSG_HASH" > "$STATE_FILE"
log "reminder sent (hash $MSG_HASH)"
