#!/bin/bash
# Undo what zt-lan-route-setup.sh did.
# Run as root: sudo bash zt-lan-route-teardown.sh

set -euo pipefail
LAN_NET="192.168.1.0/24"
ZT_NET="10.59.0.0/16"
LAN_IF="eth0"
ZT_IF="zttqh5myou"

bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }

bold "[1/3] Remove iptables rules"
for c in zt-lan-out zt-lan-in zt-lan-masq zt-lan-conntrack; do
  while iptables -C FORWARD -m comment --comment "$c" -j ACCEPT 2>/dev/null \
     || iptables -C FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -m comment --comment "$c" -j ACCEPT 2>/dev/null; do
    # pick the right delete
    if iptables -C FORWARD -m comment --comment "$c" -j ACCEPT 2>/dev/null; then
      iptables -D FORWARD -m comment --comment "$c" -j ACCEPT
    else
      iptables -D FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -m comment --comment "$c" -j ACCEPT
    fi
  done
  if iptables -t nat -C POSTROUTING -s "$ZT_NET" -o "$LAN_IF" -j MASQUERADE -m comment --comment "$c" 2>/dev/null; then
    iptables -t nat -D POSTROUTING -s "$ZT_NET" -o "$LAN_IF" -j MASQUERADE -m comment --comment "$c"
  fi
  ok "Removed rules tagged $c"
done
iptables-save > /etc/iptables/rules.v4
ok "Saved /etc/iptables/rules.v4"

bold "[2/3] Remove systemd unit"
systemctl disable --now zt-lan-route.service 2>/dev/null || true
rm -f /etc/systemd/system/zt-lan-route.service
systemctl daemon-reload
ok "Removed zt-lan-route.service"

bold "[3/3] Remove sysctl override"
rm -f /etc/sysctl.d/99-zt-forward.conf
sysctl -w net.ipv4.ip_forward=0 >/dev/null
ok "Disabled ip_forward (until reboot)"

bold "DONE. ZeroTier can no longer reach $LAN_NET through this Pi."
echo
echo "If you want to remove the ZeroTier flow rules from my.zerotier.com,"
echo "delete the two 'accept ip ...' rules you added."
