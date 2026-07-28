#!/bin/bash
# install.sh — install g90-launcher systemd units on a deployed g90 box.
#
# Run as root (or with sudo) on the target g90 box. Idempotent.
#
# What this does:
#   1. Copy ardop-ptt-bridge.service and piardopc.service to /etc/systemd/system/
#   2. systemctl daemon-reload
#   3. systemctl enable ardop-ptt-bridge.service piardopc.service
#   4. systemctl disable rigctld.service  (bridge replaces it)
#   5. systemctl restart ardop-ptt-bridge.service
#   6. systemctl restart piardopc.service
#
# This script assumes:
#   - /home/pi/ardop/ardop_ptt_bridge.py exists (the unified bridge)
#   - /home/pi/ardop/piardopc exists (the ARDOP modem binary)
#   - pat-http.service is already installed (separate)
#
# After install, the box will boot into a working ARDOP/winlink stack:
#   bridge owns FTDI cable + serves :8517/:8518/:4532
#   piardopc runs audio-only on :8515/:8516 (no -p, bridge owns FTDI)
#   pat-http runs the HTTP UI on :5000
#
# VOX on the G90 must be enabled for piardopc-internal commands
# (two-tone test, beacon) to key the radio.

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: must run as root (or sudo)" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Installing systemd units from $SCRIPT_DIR"
install -m 0644 "$SCRIPT_DIR/ardop-ptt-bridge.service" /etc/systemd/system/
install -m 0644 "$SCRIPT_DIR/piardopc.service" /etc/systemd/system/

echo "==> Installing g90-flrig wrapper to /usr/local/bin/"
install -m 0755 "$SCRIPT_DIR/../scripts/g90-flrig" /usr/local/bin/g90-flrig

echo "==> Reloading systemd"
systemctl daemon-reload

echo "==> Enabling + starting bridge and piardopc"
systemctl enable ardop-ptt-bridge.service
systemctl enable piardopc.service
systemctl restart ardop-ptt-bridge.service
sleep 1
systemctl restart piardopc.service

# Disable obsolete rigctld.service if it's installed — bridge replaces it.
if systemctl list-unit-files rigctld.service >/dev/null 2>&1; then
    echo "==> Disabling obsolete rigctld.service (bridge replaces it)"
    systemctl disable --now rigctld.service || true
fi

echo "==> Done. Status:"
systemctl --no-pager status ardop-ptt-bridge.service | head -10
echo "---"
systemctl --no-pager status piardopc.service | head -10
echo "---"
echo "==> Listeners:"
ss -lntp | grep -E ':8515|:8516|:8517|:8518|:4532|:5000' || echo "(no listeners yet — check journal)"
echo "---"
echo "REMINDER: enable VOX on the G90 for two-tone test/beacon to key the radio."