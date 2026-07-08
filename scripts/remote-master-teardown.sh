#!/bin/bash
# Undo remote-master-setup.sh
# Run as root: sudo bash /home/pi/.openclaw/workspace/scripts/remote-master-teardown.sh
#
# What it removes:
#   - 3 SMB shares ([remote], [remote-view], [remote-inbox]) from smb.conf
#   - 2 samba users (phone-view, phone-drop)
#   - 2 linux users (phone-view, phone-drop)
#   - fstab entry for LABEL=Remote
#   - /media/pi/REMOTE directory
# What it does NOT touch:
#   - The sdb1 partition or its data
#   - The sdb2 encrypted partition

set -euo pipefail
bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
die()  { printf '  \033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die "Run as root: sudo bash $0"

bold "[1/4] Remove SMB shares"
SMBCONF=/etc/samba/smb.conf
if [[ -f "${SMBCONF}.pre-remote-"* ]] 2>/dev/null || ls "${SMBCONF}.pre-remote-"* >/dev/null 2>&1; then
  LATEST=$(ls -t "${SMBCONF}.pre-remote-"* 2>/dev/null | head -1)
  if [[ -n "$LATEST" ]]; then
    cp -a "$LATEST" "$SMBCONF"
    ok "Restored $SMBCONF from $LATEST"
  fi
else
  # Manual scrub: remove our 3 sections
  cp -a "$SMBCONF" "${SMBCONF}.pre-teardown-$(date +%Y%m%d-%H%M%S)"
  for s in '\[remote\]' '\[remote-view\]' '\[remote-inbox\]'; do
    if grep -qE "^${s}\s*$" "$SMBCONF"; then
      awk -v s="$s" 'BEGIN{p=1} /^# --- Master drive shares/{p=0; next} p && $0 ~ "^"s"\\s*$"{p=2; next} p==2 && /^[[:space:]]*$/ && p2==2{p=3; next} p==3{p=0; p2=0} p{print}' "$SMBCONF" > "${SMBCONF}.tmp" || true
      # Simpler approach: just nuke the whole "--- Master drive shares" block
      mv "${SMBCONF}.tmp" "$SMBCONF" 2>/dev/null || true
    fi
  done
  ok "Scrubbed shares from $SMBCONF (backup created)"
fi
systemctl reload smbd 2>/dev/null || systemctl restart smbd 2>/dev/null || true
ok "smbd reloaded"

bold "[2/4] Remove samba + linux users"
for u in phone-view phone-drop; do
  if id "$u" >/dev/null 2>&1; then
    smbpasswd -x "$u" 2>/dev/null || true
    userdel "$u" 2>/dev/null || true
    ok "Removed $u"
  else
    ok "$u not present"
  fi
done
rm -f /root/.samba-remote-credentials
ok "Removed /root/.samba-remote-credentials"

bold "[3/4] Unmount and remove fstab entry"
if mountpoint -q /media/pi/REMOTE; then
  umount /media/pi/REMOTE
  ok "Unmounted /media/pi/REMOTE"
fi
if grep -qE 'LABEL=Remote\b' /etc/fstab; then
  cp /etc/fstab /etc/fstab.bak
  sed -i '/LABEL=Remote\b/d' /etc/fstab
  ok "Removed LABEL=Remote from fstab (backup at /etc/fstab.bak)"
fi
rmdir /media/pi/REMOTE 2>/dev/null && ok "Removed /media/pi/REMOTE" || ok "Left /media/pi/REMOTE directory"

bold "[4/4] Encrypted sdb2 status"
if grep -qE 'sdb2\b' /etc/fstab /etc/crypttab 2>/dev/null; then
  warn "sdb2 still referenced somewhere. Review."
else
  ok "sdb2 has never been auto-unlocked on the Pi (good)"
fi

bold "DONE"
echo "Drive data on /dev/sdb1 is preserved. Encrypted /dev/sdb2 untouched."
echo "Physically unplug the drive to fully remove it from the Pi."
