#!/bin/bash
#
# usb-watchdog.sh — alert when the USB SSD drops, attempt soft recovery
#
# Run as a systemd service. Polls every 5 seconds.
#
# Behavior:
#   - If /dev/sda disappears, wait 15s; if still gone, send a Telegram alert.
#   - When /dev/sda reappears, run a quick fsck then remount.
#   - Keeps a state file in /run/usb-watchdog.state so it only fires on
#     state changes (drop, recover), not on every poll.
#
# Config (env):
#   TG_BOT_TOKEN  - Telegram bot token (required for alerts)
#   TG_CHAT_ID    - Chat to alert (required for alerts)
#   WATCH_LABEL   - fstab label of the drive to watch (default: Remote)
#   WATCH_MOUNT   - mount point (default: /media/pi/REMOTE)
#   WATCH_DEVPATH - /dev path to look for (default: /dev/sda)

set -u

WATCH_LABEL="${WATCH_LABEL:-Remote}"
WATCH_MOUNT="${WATCH_MOUNT:-/media/pi/REMOTE}"
WATCH_DEVPATH="${WATCH_DEVPATH:-/dev/sda}"
STATE_FILE="/run/usb-watchdog.state"
LOG_TAG="usb-watchdog"

log() {
  logger -t "$LOG_TAG" "$1"
  echo "$(date -Is) $1" >> /var/log/usb-watchdog.log
}

tg_alert() {
  local msg="$1"
  if [ -n "${TG_BOT_TOKEN:-}" ] && [ -n "${TG_CHAT_ID:-}" ]; then
    curl -sS -X POST \
      "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
      -d chat_id="$TG_CHAT_ID" \
      -d text="🚨 usb-watchdog: $msg" \
      -d parse_mode=Markdown \
      --max-time 10 >/dev/null 2>&1 || true
  fi
}

device_present() {
  [ -b "$WATCH_DEVPATH" ]
}

mounted_here() {
  mount | grep -q " on $WATCH_MOUNT "
}

prev_state="up"
[ -f "$STATE_FILE" ] && prev_state="$(cat "$STATE_FILE")"

if device_present && mounted_here; then
  # Healthy
  if [ "$prev_state" != "up" ]; then
    log "Drive recovered; /media/pi/REMOTE mounted."
    tg_alert "✅ usb-watchdog: drive recovered, $WATCH_MOUNT is back."
  fi
  echo "up" > "$STATE_FILE"
elif device_present && ! mounted_here; then
  # Device there, mount missing — try to mount (after a quick fsck if dirty)
  log "Device $WATCH_DEVPATH present but $WATCH_MOUNT not mounted; attempting mount."
  if sudo mountpoint -q "$WATCH_MOUNT" 2>/dev/null; then
    sudo umount "$WATCH_MOUNT" 2>/dev/null || true
  fi
  if sudo fsck.ext4 -n "$WATCH_DEVPATH"1 >/dev/null 2>&1; then
    sudo mount LABEL="$WATCH_LABEL" "$WATCH_MOUNT" && \
      log "Remounted $WATCH_MOUNT clean." || \
      log "Remount failed."
  else
    log "Filesystem dirty; running fsck (non-interactive)."
    sudo fsck.ext4 -f -y "$WATCH_DEVPATH"1 >/tmp/usb-watchdog-fsck.log 2>&1 && \
      sudo mount LABEL="$WATCH_LABEL" "$WATCH_MOUNT" && \
      log "Repaired + remounted $WATCH_MOUNT." || \
      log "fsck failed; check /tmp/usb-watchdog-fsck.log"
  fi
  echo "recovering" > "$STATE_FILE"
elif ! device_present; then
  # Drive gone
  if [ "$prev_state" != "down" ]; then
    log "Drive $WATCH_DEVPATH disappeared from USB bus. Waiting 15s before alerting."
    echo "down_pending" > "$STATE_FILE"
  elif [ "$prev_state" = "down_pending" ]; then
    sleep 15
    if ! device_present; then
      log "Drive still gone after 15s. Alerting."
      tg_alert "❌ usb-watchdog: $WATCH_DEVPATH dropped off USB bus. *Nomadpi may hang* if openclaw tries to read $WATCH_MOUNT. Unplug/replug the drive to recover."
      echo "down" > "$STATE_FILE"
    else
      log "Drive came back within 15s. No alert sent."
      echo "up" > "$STATE_FILE"
    fi
  fi
fi
