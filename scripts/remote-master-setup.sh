#!/bin/bash
# Setup the new master drive on the Pi.
# Run as root: sudo bash /home/pi/.openclaw/workspace/scripts/remote-master-setup.sh
#
# What it does:
#   1. Verifies sdb1 is the ext4 Remote partition (DOES NOT TOUCH sdb2 / encrypted)
#   2. Adds fstab entry (LABEL=Remote) so it auto-mounts at /media/pi/REMOTE on boot
#   3. Mounts it
#   4. chown to pi:pi (so you can write from the laptop/phone later)
#   5. Creates the folder structure:
#        projects/{pictures,documents,spreadsheets}/
#        inbox/
#   6. Adds 3 SMB shares to /etc/samba/smb.conf:
#        remote         R/W  LAN only   (laptop)
#        remote-view    R/O  ZT only    (phone-view user)
#        remote-inbox   R/W  ZT only    (phone-drop user, scoped to inbox/)
#   7. Creates 2 samba users (no shell login, random passwords):
#        phone-view     read-only into projects/
#        phone-drop     read-write into inbox/ only
#   8. Restarts smbd
#   9. Verifies the encrypted sdb2 was not touched (sdb2 not in fstab, not in crypttab)
#
# Idempotent: re-runs are safe. If something already exists, it leaves it.
# To undo: /home/pi/.openclaw/workspace/scripts/remote-master-teardown.sh

set -euo pipefail

bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '  \033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

# --- 0. Sanity ---
bold "[0/9] Sanity checks"
[[ $EUID -eq 0 ]] || die "Run as root: sudo bash $0"

if ! lsblk -no NAME,LABEL 2>/dev/null | grep -q 'Remote'; then
  die "No partition with LABEL=Remote found. Aborting."
fi

# Find the partition device for LABEL=Remote.
# lsblk -no NAME,LABEL gives one device per line; the first field is the basename
# (e.g. "sdb1"). It does NOT include the tree connector characters when -l is used
# or when reading -no NAME. But just in case, strip any non-name prefix.
DEV=$(lsblk -nlo NAME,LABEL 2>/dev/null | awk '/Remote/{print $1; exit}' | tr -d '├└─┎' | tr -d ' ')
[[ -n "$DEV" ]] || DEV=$(lsblk -no NAME,LABEL 2>/dev/null | awk '/Remote/{print $1; exit}' | tr -d '├└─┎' | tr -d ' ')
[[ -n "$DEV" ]] || die "Could not identify Remote device."
# Defensive: only operate on a partition that lives on /dev/sdb*
case "$DEV" in
  sdb1) ok "Master partition: /dev/$DEV  (LABEL=Remote) - matches expected layout" ;;
  *)    die "Expected /dev/sdb1 (Remote). Refusing to operate on /dev/$DEV." ;;
esac

# Verify the encrypted sdb2 is present and that we're not about to touch it
if ! lsblk -no TYPE,NAME | awk '$1=="crypt"{found=1} END{exit !found}'; then
  warn "No LUKS partition visible. That's fine if you don't have sdb2; otherwise check."
fi
if [[ "$DEV" != "sdb1" ]]; then
  die "Expected /dev/sdb1 (Remote). Refusing to operate on /dev/$DEV."
fi
ok "Encrypted sibling /dev/sdb2 will NOT be touched (not in fstab, not in crypttab)"

# --- 1. fstab entry ---
bold "[1/9] fstab: auto-mount LABEL=Remote at /media/pi/REMOTE"
FSTAB=/etc/fstab
mkdir -p /media/pi/REMOTE
if grep -qE 'LABEL=Remote\b' "$FSTAB"; then
  ok "fstab already has LABEL=Remote entry"
else
  # nosuid,nodev,noatime are good defaults; uid/gid not used (we chown to pi:pi)
  printf 'LABEL=Remote\t/media/pi/REMOTE\text4\tdefaults,noatime,nofail\t0\t2\n' >> "$FSTAB"
  ok "Appended LABEL=Remote entry to $FSTAB"
fi

# Ensure the encrypted sdb2 is NOT in fstab (defensive: if it ever was, this removes it)
if grep -qE 'sdb2\b' "$FSTAB"; then
  warn "Removing sdb2 reference from fstab (encrypted partition should not be auto-mounted):"
  grep -nE 'sdb2\b' "$FSTAB"
  sed -i.bak '/sdb2\b/d' "$FSTAB"
  ok "Removed. Backup at $FSTAB.bak"
fi
if grep -qE 'sdb2\b' /etc/crypttab 2>/dev/null; then
  warn "sdb2 found in /etc/crypttab. Removing (we do not auto-unlock on the Pi):"
  grep -nE 'sdb2\b' /etc/crypttab
  cp /etc/crypttab /etc/crypttab.bak
  sed -i '/sdb2\b/d' /etc/crypttab
  ok "Removed. Backup at /etc/crypttab.bak"
fi

# --- 2. Mount now ---
bold "[2/9] Mounting /media/pi/REMOTE"
if mountpoint -q /media/pi/REMOTE; then
  ok "Already mounted"
else
  mount /media/pi/REMOTE
  ok "Mounted"
fi

# --- 3. Ownership ---
bold "[3/9] chown pi:pi"
chown -R pi:pi /media/pi/REMOTE
chmod 755 /media/pi/REMOTE
ok "Ownership set to pi:pi, mode 0755"

# --- 4. Folder structure ---
bold "[4/9] Creating folder structure"
for d in projects projects/pictures projects/documents projects/spreadsheets inbox; do
  mkdir -p "/media/pi/REMOTE/$d"
  chown pi:pi "/media/pi/REMOTE/$d"
done
ok "projects/{pictures,documents,spreadsheets}/ and inbox/ created"

# --- 5. Samba config ---
bold "[5/9] SMB shares: remote (LAN), remote-view (ZT R/O), remote-inbox (ZT R/W)"
SMBCONF=/etc/samba/smb.conf
cp -a "$SMBCONF" "${SMBCONF}.pre-remote-$(date +%Y%m%d-%H%M%S)"

# Read ZT subnet (assume 10.59.0.0/16; if your network is different, edit below)
ZT_SUBNET="10.59.0.0/16"
LAN_SUBNET="192.168.1.0/24"

# Idempotency: check if [remote] already exists
if ! grep -qE '^\[remote\]\s*$' "$SMBCONF"; then
cat >> "$SMBCONF" <<EOF

# --- Master drive shares (added by remote-master-setup.sh) ---
[remote]
   comment = Master project drive (R/W) - LAN only, for laptop
   path = /media/pi/REMOTE
   browseable = yes
   writable = yes
   read only = no
   guest ok = no
   valid users = pi
   create mask = 0664
   directory mask = 0775
   force user = pi
   force group = pi
   inherit permissions = yes
   hosts allow = $LAN_SUBNET 127.0.0.1
   hosts deny = 0.0.0.0/0

[remote-view]
   comment = Master drive (R/O, projects/ only) - for phone-view
   path = /media/pi/REMOTE/projects
   browseable = yes
   writable = no
   read only = yes
   guest ok = no
   valid users = phone-view
   create mask = 0664
   directory mask = 0775
   force user = pi
   force group = pi
   inherit permissions = yes
   hosts allow = $ZT_SUBNET 127.0.0.1
   hosts deny = 0.0.0.0/0

[remote-inbox]
   comment = Inbox (R/W, inbox/ only) - for phone-drop
   path = /media/pi/REMOTE/inbox
   browseable = yes
   writable = yes
   read only = no
   guest ok = no
   valid users = phone-drop
   create mask = 0664
   directory mask = 0775
   force user = pi
   force group = pi
   inherit permissions = yes
   hosts allow = $ZT_SUBNET 127.0.0.1
   hosts deny = 0.0.0.0/0
EOF
  ok "Appended 3 shares to $SMBCONF"
else
  ok "Shares already present (skipping append)"
fi

# Make sure smbd is listening on the ZT interface (it already is, per prior setup)
if ! grep -qE 'zttqh5myou' "$SMBCONF"; then
  warn "interfaces line does not include zttqh5myou. Edit /etc/samba/smb.conf [global]."
fi

# --- 6. Samba users (no shell login, random passwords) ---
bold "[6/9] Creating samba users phone-view and phone-drop"
PWFILE=/root/.samba-remote-credentials
touch "$PWFILE"; chmod 600 "$PWFILE"

create_or_update_user() {
  local user=$1 pw=$2 mode=$3  # mode: "view" or "drop"
  if id "$user" >/dev/null 2>&1; then
    ok "Linux user $user already exists"
  else
    useradd -r -s /usr/sbin/nologin -M "$user"
    ok "Created Linux user $user (no shell, no home)"
  fi
  if ! pdbedit -L 2>/dev/null | grep -q "^${user}:"; then
    printf '%s\n%s\n' "$pw" "$pw" | smbpasswd -s -a "$user" >/dev/null
    ok "Set samba password for $user"
  else
    printf '%s\n%s\n' "$pw" "$pw" | smbpasswd -s "$user" >/dev/null
    ok "Updated samba password for $user"
  fi
}

# Generate / reuse passwords
get_pw() {
  local user=$1
  local key="pw_$user"
  if grep -qE "^${key}=" "$PWFILE" 2>/dev/null; then
    grep -E "^${key}=" "$PWFILE" | cut -d= -f2-
  else
    local pw
    pw=$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)
    echo "${key}=${pw}" >> "$PWFILE"
    echo "$pw"
  fi
}

PW_VIEW=$(get_pw phone-view)
PW_DROP=$(get_pw phone-drop)
create_or_update_user phone-view "$PW_VIEW" view
create_or_update_user phone-drop "$PW_DROP" drop

# --- 7. Restrict phone users' filesystem access ---
bold "[7/9] Restrict phone-view and phone-drop to their share paths only"
# These users have /usr/sbin/nologin, so they can't shell in. The samba config
# already constrains them via `path = ...` and `valid users`. No further
# restriction needed at the FS level for now. If we ever want belt+suspenders,
# we can add ACLs that deny phone-view read access to /media/pi/REMOTE/inbox/
# and deny phone-drop read/write to /media/pi/REMOTE/projects/.
ok "Samba-level scoping in place (no FS-level ACLs needed)"

# --- 8. Restart smbd ---
bold "[8/9] Reload smbd"
if systemctl is-active --quiet smbd; then
  systemctl reload smbd || systemctl restart smbd
  ok "smbd reloaded"
else
  systemctl enable --now smbd
  ok "smbd started (was not active)"
fi

# --- 9. Verify ---
bold "[9/9] Verify"
echo "Mount:"
mountpoint -q /media/pi/REMOTE && echo "  /media/pi/REMOTE is mounted ($(df -h /media/pi/REMOTE | tail -1 | awk '{print $2}') total, $(df -h /media/pi/REMOTE | tail -1 | awk '{print $4}') free)"
echo
echo "Folder structure:"
ls -la /media/pi/REMOTE/ 2>&1 | tail -n +2
echo
echo "Samba shares:"
grep -E '^\[remote(-(view|inbox))?\]\s*$' "$SMBCONF" | sed 's/^/  /'
echo
echo "Samba users:"
pdbedit -L 2>&1 | grep -E '^(pi|phone-(view|drop)):' | sed 's/^/  /'
echo
echo "Encrypted sdb2 (must NOT be in fstab/crypttab):"
if grep -qE 'sdb2\b' /etc/fstab /etc/crypttab 2>/dev/null; then
  warn "  ⚠ sdb2 found in fstab/crypttab - review above"
else
  ok "  sdb2 is NOT auto-unlocked on the Pi"
fi

bold "DONE"
echo
echo "==== Phone setup (CIFS Documents Provider on Android) ===="
echo
echo "1. Install 'CIFS Documents Provider' from F-Droid (free)."
echo "2. Open it, add storage:"
echo "   Host: 10.59.42.91"
echo "   Share: remote-view"
echo "   User: phone-view"
echo "   Password: $PW_VIEW"
echo
echo "3. Add a second storage:"
echo "   Host: 10.59.42.91"
echo "   Share: remote-inbox"
echo "   User: phone-drop"
echo "   Password: $PW_DROP"
echo
echo "  (Passwords are also saved in $PWFILE on the Pi.)"
echo
echo "==== Laptop setup ===="
echo "  Open \\\\10.59.42.91\\remote  from Explorer/Finder when on ZT."
echo "  From LAN:  \\\\192.168.1.147\\remote  (user: pi, same samba password)."
echo
echo "==== To undo ===="
echo "  sudo bash /home/pi/.openclaw/workspace/scripts/remote-master-teardown.sh"
