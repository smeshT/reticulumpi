#!/usr/bin/env bash
# slate-revoke.sh — Kill switch for Slate's scoped sudo.
#
# Removes the sudoers drop-in so Slate (running as user `pi`) loses
# the NOPASSWD grant. Run as `pi` with sudo.
#
# Usage:
#   sudo /home/pi/.openclaw/workspace/scripts/slate-revoke.sh
#   sudo /home/pi/.openclaw/workspace/scripts/slate-revoke.sh --yes
#
# What it does:
#   1. Removes /etc/sudoers.d/020_slate
#   2. Verifies the file is gone
#   3. Prints a one-liner confirming the revocation
#
# Safe to run multiple times (idempotent).

set -euo pipefail

SUDOERS_FILE="/etc/sudoers.d/020_slate"

if [[ "${1:-}" != "--yes" && "${1:-}" != "-y" ]]; then
    echo "This will revoke Slate's scoped sudo access."
    echo "Re-run with --yes to confirm."
    exit 1
fi

if [[ -f "$SUDOERS_FILE" ]]; then
    sudo rm -f "$SUDOERS_FILE"
    echo "[$(date -Iseconds)] Revoked: $SUDOERS_FILE removed."
else
    echo "[$(date -Iseconds)] Nothing to do: $SUDOERS_FILE not present."
fi

# Belt-and-braces: confirm sudo no longer accepts the grant.
if sudo -n -l 2>&1 | grep -q "SLATE_PKG\|SLATE_SVC\|SLATE_CONF\|SLATE_USR\|SLATE_FW"; then
    echo "WARNING: Sudo still shows SLATE_* rules. Investigate manually."
    exit 2
else
    echo "Confirmed: SLATE_* rules no longer present in sudo -l output."
fi
