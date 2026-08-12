#!/bin/bash
# install.sh — install g90-launcher systemd units on a deployed g90 box.
#
# Run as root (or with sudo) on the target g90 box. Idempotent.
#
# What this does:
#   1. Copy ardop-ptt-bridge.service and piardopc.service to /etc/systemd/system/
#   2. systemctl daemon-reload
#   3. systemctl disable --now ardop-ptt-bridge.service piardopc.service
#      (units are installed INERT — no auto-start. The launcher's Start
#      button is the only path to enable + start them. This is deliberate:
#      see the comment in each unit file.)
#   4. Disable obsolete rigctld.service if present (bridge replaces it)
#
# This script assumes:
#   - /home/pi/ardop/ardop_ptt_bridge.py exists (the unified bridge)
#   - /home/pi/ardop/piardopc exists (the ARDOP modem binary)
#   - pat-http.service is already installed (separate)
#
# The unit templates in this directory deliberately have NO [Install]
# section — systemd can't `enable` a unit without one, so even if a
# fresh image's first-boot hook ran `systemctl enable ...` it would
# fail with "unit has no install configuration". That makes "inert
# install" a property of the unit file itself, not a step this script
# could forget. The launcher is the only thing that re-enables them,
# and only when the operator clicks Start.
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

# Units have no [Install] section, so they're already inert. No
# `enable`, no auto-start. The launcher Start button calls
# `sudo -n systemctl enable --now <unit>` to bring them up.
echo "==> Units installed inert (no auto-start, no enable)"
systemctl is-enabled ardop-ptt-bridge.service piardopc.service 2>&1 || true

# Disable obsolete rigctld.service if it's installed — bridge replaces it.
# rigctld stays enabled on digipat builds where the bridge isn't installed;
# this only fires when both unit files coexist.
if systemctl list-unit-files rigctld.service >/dev/null 2>&1 \
   && systemctl list-unit-files ardop-ptt-bridge.service >/dev/null 2>&1; then
    echo "==> Disabling obsolete rigctld.service (bridge replaces it)"
    systemctl disable --now rigctld.service || true
fi

echo "==> Done. Unit file state:"
for u in ardop-ptt-bridge.service piardopc.service; do
    printf "  %-32s enabled=%s active=%s\n" "$u" \
        "$(systemctl is-enabled $u 2>&1)" \
        "$(systemctl is-active $u 2>&1)"
done
echo "---"
echo "REMINDER: enable VOX on the G90 before clicking Start on the launcher."