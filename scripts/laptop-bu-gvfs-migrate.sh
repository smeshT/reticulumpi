#!/bin/bash
# Update laptop BU script + service to use the GVFS path now that fstab is gone.
# Run on the laptop, as the regular user (jg).
set -euo pipefail
bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
die()  { printf '  \033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

GVFS_PATH="/run/user/1000/gvfs/smb-share:server=192.168.1.147,share=remote,user=pi"
ROTATE="$HOME/bin/remote-bu-rotate"
SERVICE="$HOME/.config/systemd/user/remote-bu.service"

# --- 1. verify the GVFS mount is actually reachable ---
bold "[1/5] Verify the GVFS path"
if [[ ! -d "$GVFS_PATH" ]]; then
  echo "  ! GVFS path does not exist. Trying to mount..."
  echo "  (You'll be prompted for the pi samba password if it's not keyring-stored)"
  echo
  # Try to mount with stored creds
  gio mount "smb://192.168.1.147/remote" 2>&1 || die "gio mount failed. Run it manually with the password first."
  sleep 1
fi
if [[ ! -d "$GVFS_PATH" ]]; then
  die "GVFS path still not found at $GVFS_PATH. Run 'ls -la /run/user/\$(id -u)/gvfs/' to see what's there."
fi
ls "$GVFS_PATH" | head -5
ok "GVFS path is live: $GVFS_PATH"

# --- 2. update the rotation script SRC= line ---
bold "[2/5] Update SRC in $ROTATE"
if [[ ! -f "$ROTATE" ]]; then
  die "Rotation script not found at $ROTATE"
fi
sed -i "s|^SRC=.*$|SRC=\"$GVFS_PATH\"|" "$ROTATE"
ok "Updated SRC="
head -5 "$ROTATE" | sed 's/^/    /'

# --- 3. update the service ExecStartPre to ensure the GVFS mount is up ---
bold "[3/5] Update $SERVICE"
if [[ ! -f "$SERVICE" ]]; then
  die "Service file not found at $SERVICE"
fi
# Add ExecStartPre=gio mount (idempotent - if already mounted, it's a no-op)
if grep -q 'ExecStartPre=' "$SERVICE"; then
  ok "ExecStartPre already present"
else
  sed -i '/^\[Service\]/a ExecStartPre=/usr/bin/gio mount "smb://192.168.1.147/remote"' "$SERVICE"
  ok "Added ExecStartPre=gio mount"
fi
# Also add graphical-session.target wait
if grep -q 'graphical-session.target' "$SERVICE"; then
  ok "graphical-session.target already in [Unit]"
else
  sed -i '/^After=network-online.target/a Wants=graphical-session.target\nAfter=graphical-session.target' "$SERVICE"
  ok "Added graphical-session.target dependency"
fi
cat "$SERVICE"

# --- 4. reload + test ---
bold "[4/5] Reload + run BU once"
systemctl --user daemon-reload
systemctl --user start remote-bu.service
echo "Service status:"
systemctl --user status remote-bu.service --no-pager -l 2>&1 | tail -8

# --- 5. verify ---
bold "[5/5] Verify the snapshot"
ls /mnt/sda8/remote_backups/REMOTE-boot-0/ | head -10
echo
echo "Disk usage of BU area:"
df -h /mnt/sda8 | tail -1
echo
du -sh /mnt/sda8/remote_backups/REMOTE-boot-* 2>/dev/null
echo
bold "DONE"
echo
echo "==== Next boot ===="
echo "  1. logind user session starts"
echo "  2. graphical-session.target fires (your desktop login)"
echo "  3. GVFS comes up; ExecStartPre=gio mount triggers if not already"
echo "  4. remote-bu.service runs the rsync rotation"
echo
echo "==== If it still fails on next boot, check: ===="
echo "  journalctl --user -u remote-bu.service -n 30"
echo "  ls -la /run/user/\$(id -u)/gvfs/"
