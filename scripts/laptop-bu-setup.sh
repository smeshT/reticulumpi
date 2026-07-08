#!/bin/bash
# Laptop-side: mount the Pi's share + 7-boot rotating BU with linked-tree snapshots.
# Run as your normal user on Ubuntu. Re-runnable.
#
# What it does (in order):
#   1. Installs cifs-utils and rsync (apt)
#   2. Creates /mnt/remote and /etc/samba/creds with chmod 600
#   3. Prompts for the Pi's samba password (writes to creds file)
#   4. Adds an /etc/fstab entry to auto-mount //192.168.1.147/remote at /mnt/remote
#   5. Tests the mount manually
#   6. Creates ~/BU/REMOTE-boot-{0..6}/ (the 7 snapshot dirs)
#   7. Writes the rotation script at ~/bin/remote-bu-rotate
#   8. Writes the systemd user service ~/.config/systemd/user/remote-bu.service
#   9. Enables lingering so user services run at boot
#  10. Runs the BU once now so you can see it work before rebooting
#
# To undo: bash /home/pi/.../laptop-bu-teardown.sh   (or follow the manual steps printed at the end)

set -euo pipefail
bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '  \033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

MOUNT=/mnt/remote
PI_IP=192.168.1.147
SHARE=remote
CREDS=/etc/samba/creds-pi
BU_ROOT="/mnt/sda8/remote_backups"
ROTATE_SCRIPT="$HOME/bin/remote-bu-rotate"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/remote-bu.service"

[[ $EUID -ne 0 ]] || die "Run as your normal user, NOT root. Re-run without sudo."

# --- 1. apt deps ---
bold "[1/10] Installing cifs-utils and rsync"
if dpkg -s cifs-utils >/dev/null 2>&1 && dpkg -s rsync >/dev/null 2>&1; then
  ok "cifs-utils and rsync already installed"
else
  sudo apt-get update -qq
  sudo apt-get install -y cifs-utils rsync
  ok "Installed cifs-utils, rsync"
fi

# --- 2. mount point + creds file ---
bold "[2/10] Mount point and credentials file"
sudo mkdir -p "$MOUNT"
ok "Mount point $MOUNT exists"

if [[ -f "$CREDS" ]]; then
  ok "Creds file $CREDS already exists"
else
  sudo touch "$CREDS"
  sudo chmod 600 "$CREDS"
  sudo chown root:root "$CREDS"
  ok "Created $CREDS (mode 600)"
fi

# --- 3. password into creds file ---
bold "[3/10] Samba password for user 'pi' on the Pi"
if grep -qE '^password=' "$CREDS" 2>/dev/null && [[ -s "$CREDS" ]]; then
  ok "Password already in $CREDS (skipping prompt)"
else
  printf 'username=pi\n' | sudo tee "$CREDS" >/dev/null
  sudo chmod 600 "$CREDS"
  # Read password silently into a tmp file, then append and shred the tmp
  TMPF=$(mktemp)
  trap 'shred -u "$TMPF" 2>/dev/null || rm -f "$TMPF"' EXIT
  while :; do
    read -r -s -p "  Pi samba password for 'pi' (input hidden): " pw1; echo
    [[ -n "$pw1" ]] || { warn "empty, try again"; continue; }
    read -r -s -p "  Confirm: " pw2; echo
    [[ "$pw1" == "$pw2" ]] || { warn "mismatch, try again"; continue; }
    break
  done
  printf 'password=%s\n' "$pw1" | sudo tee -a "$CREDS" >/dev/null
  unset pw1 pw2
  sudo chmod 600 "$CREDS"
  ok "Password stored in $CREDS (mode 600, never echoed)"
fi

# --- 4. fstab ---
bold "[4/10] /etc/fstab entry for $MOUNT"
FSTAB=/etc/fstab
FSTAB_LINE="//$PI_IP/$SHARE  $MOUNT  cifs  credentials=$CREDS,uid=$(id -u),gid=$(id -g),_netdev,x-systemd.automount,iocharset=utf8,vers=3.0  0  0"
if grep -qE "$PI_IP/$SHARE.*$MOUNT" "$FSTAB"; then
  ok "fstab already has entry for $MOUNT"
else
  echo "$FSTAB_LINE" | sudo tee -a "$FSTAB" >/dev/null
  ok "Appended to $FSTAB:"
  echo "    $FSTAB_LINE"
fi

# --- 5. test mount ---
bold "[5/10] Test mount"
if mountpoint -q "$MOUNT"; then
  ok "$MOUNT already mounted"
else
  sudo mount "$MOUNT" || die "Mount failed. Check: is the Pi on? Is 192.168.1.147 reachable? Is the password right?"
  ok "Mounted $MOUNT"
fi
echo "  Files visible at $MOUNT:"
ls "$MOUNT" 2>&1 | sed 's/^/    /'

# --- 6. BU dirs ---
bold "[6/10] BU snapshot directories (7 boots)"
mkdir -p "$BU_ROOT"
for i in 0 1 2 3 4 5 6; do
  mkdir -p "$BU_ROOT/REMOTE-boot-$i"
done
ok "$BU_ROOT/REMOTE-boot-{0..6}/ created"

# --- 7. rotation script ---
bold "[7/10] Rotation script at $ROTATE_SCRIPT"
mkdir -p "$(dirname "$ROTATE_SCRIPT")"
cat > "$ROTATE_SCRIPT" <<'BASH'
#!/bin/bash
# 7-boot rotating BU using rsync --link-dest.
# Each snapshot is a full-looking tree, but unchanged files are hard-linked
# to the previous snapshot. Disk usage = 1x of source + small delta per boot.

set -euo pipefail
SRC=/mnt/remote          # the mounted share
DST_ROOT="/mnt/sda8/remote_backups"      # BU root
N=7                      # number of snapshots to keep

# Sanity: source must be mounted
if ! mountpoint -q "$SRC"; then
  echo "ERROR: $SRC is not mounted. Skipping BU." >&2
  exit 1
fi

# Rotate: oldest gets deleted, others shift up by 1
for i in $(seq $((N-1)) -1 1); do
  if [[ -d "$DST_ROOT/REMOTE-boot-$i" ]]; then
    if [[ $i -eq $((N-1)) ]]; then
      rm -rf "$DST_ROOT/REMOTE-boot-$i"
    else
      mv "$DST_ROOT/REMOTE-boot-$i" "$DST_ROOT/REMOTE-boot-$((i+1))"
    fi
  fi
done

# boot-0 becomes the new "previous" reference
mv "$DST_ROOT/REMOTE-boot-0" "$DST_ROOT/REMOTE-boot-1"

# Run the actual rsync: link-dest to the new boot-1 (= old boot-0)
rsync -a --delete --link-dest="$DST_ROOT/REMOTE-boot-1" \
      "$SRC/" "$DST_ROOT/REMOTE-boot-0/"

# Sanity report
echo "BU done. Newest: boot-0"
du -sh "$DST_ROOT"/REMOTE-boot-* 2>/dev/null
BASH
chmod +x "$ROTATE_SCRIPT"
ok "Wrote $ROTATE_SCRIPT"

# --- 8. systemd user service ---
bold "[8/10] systemd user service: $SERVICE_FILE"
mkdir -p "$SERVICE_DIR"
cat > "$SERVICE_FILE" <<'UNIT'
[Unit]
Description=Remote BU - 7-boot rotating rsync snapshot of /mnt/remote
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=%h/bin/remote-bu-rotate
Nice=10
IOSchedulingClass=best-effort

[Install]
WantedBy=default.target
UNIT
ok "Wrote $SERVICE_FILE"

# --- 9. enable + lingering ---
bold "[9/10] Enable + logind lingering"
systemctl --user daemon-reload
systemctl --user enable remote-bu.service
ok "Enabled user service remote-bu.service"

if ! loginctl show-user "$USER" 2>/dev/null | grep -q 'Linger=yes'; then
  sudo loginctl enable-linger "$USER"
  ok "Enabled logind linger for $USER (so user services run at boot even before login)"
else
  ok "Linger already enabled for $USER"
fi

# --- 10. run now ---
bold "[10/10] Run the BU once now (so you can see it work)"
"$ROTATE_SCRIPT"
echo
echo "Snapshot contents:"
ls -la "$BU_ROOT/REMOTE-boot-0/" 2>&1 | head -10

bold "DONE"
echo
echo "==== What happens on next boot ===="
echo "  - /mnt/remote auto-mounts (fstab + x-systemd.automount)"
echo "  - remote-bu.service fires, runs the rotate+rsync"
echo "  - You can see logs:  journalctl --user -u remote-bu.service -n 50"
echo "  - You can run it manually:  systemctl --user start remote-bu.service"
echo
echo "==== To undo ===="
echo "  1. systemctl --user disable --now remote-bu.service"
echo "  2. rm $SERVICE_FILE && systemctl --user daemon-reload"
echo "  3. Remove the fstab line containing $PI_IP"
echo "  4. sudo umount $MOUNT && sudo rmdir $MOUNT"
echo "  5. sudo shred -u $CREDS"
echo "  6. rm -rf $BU_ROOT"
echo "  7. sudo loginctl disable-linger $USER   (if you want to revert that too)"
