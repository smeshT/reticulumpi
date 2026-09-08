#!/bin/bash
# prepare-lxmd-dirs.sh — create the directories lxmd needs at runtime.
#
# lxmd.service runs with ProtectSystem=strict + ReadWritePaths=, so any
# directory it writes to MUST exist before the unit starts. systemd
# won't auto-create them. This script is the install-time hook.
#
# Idempotent: re-running is harmless.

set -e

LXMD_STORAGE="/home/pi/.lxmd"
RETICULUM_STORAGE="/home/pi/.reticulum"

# Create directories (mkdir -p is a no-op if they exist).
mkdir -p "$LXMD_STORAGE"

# Ensure ownership matches what lxmd.service expects (User=pi).
# We do this unconditionally so a hand-fix from a previous failed
# setup is corrected on re-run.
chown -R pi:pi "$LXMD_STORAGE"

echo "lxmd: directories ready"
echo "  $LXMD_STORAGE (owned by pi:pi)"
echo
echo "Next: enable + start lxmd"
echo "  sudo systemctl enable --now lxmd.service"
