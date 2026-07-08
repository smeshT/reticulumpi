#!/bin/bash
# One-shot: route LAN (192.168.1.0/24) out of nomadpi for ZeroTier peers.
# Run as root on the Pi: sudo bash zt-lan-route-setup.sh
#
# What it does:
#   1. Enables IPv4 forwarding (persist via /etc/sysctl.d/99-zt-forward.conf)
#   2. Adds iptables NAT + forward rules for ZeroTier subnet -> eth0
#   3. Saves rules so they survive reboot
#   4. Installs a tiny systemd unit (idempotent on boot) as belt-and-suspenders
#
# Re-runnable: every step checks for existing config before changing it.
# To undo: see /home/pi/.openclaw/workspace/scripts/zt-lan-route-teardown.sh

set -euo pipefail

LAN_NET="192.168.1.0/24"
ZT_NET="10.59.0.0/16"           # your ZeroTier network range
LAN_IF="eth0"
ZT_IF="zttqh5myou"              # ZeroTier interface on this Pi

bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }

# --- 0. Sanity ---
bold "[0/5] Sanity checks"
if [[ $EUID -ne 0 ]]; then
  echo "  ✗ Please run as root: sudo bash $0"; exit 1
fi
if ! ip link show "$ZT_IF" >/dev/null 2>&1; then
  warn "Interface $ZT_IF not found. Listing zerotier interfaces:"
  ip -br link | grep -i zt || true
  echo "  Edit ZT_IF at the top of this script and re-run."
  exit 1
fi
if ! ip link show "$LAN_IF" >/dev/null 2>&1; then
  warn "Interface $LAN_IF not found. Listing LAN interfaces:"
  ip -br addr | grep -v lo | head
  exit 1
fi
ok "ZT_IF=$ZT_IF  LAN_IF=$LAN_IF"

# --- 1. ip_forward persist ---
bold "[1/5] Persist net.ipv4.ip_forward=1"
CONF=/etc/sysctl.d/99-zt-forward.conf
if [[ -f $CONF ]] && grep -q '^net.ipv4.ip_forward = 1' "$CONF"; then
  ok "Already set in $CONF"
else
  echo 'net.ipv4.ip_forward = 1' > "$CONF"
  sysctl -p "$CONF" >/dev/null
  ok "Wrote $CONF and applied"
fi

# --- 2. iptables rules (idempotent) ---
bold "[2/5] iptables: forward + NAT for $ZT_NET -> $LAN_IF"

ensure_forward() {  # $1=src-if  $2=dst-if  $3=comment
  local src=$1 dst=$2 cmt=$3
  if ! iptables -C FORWARD -i "$src" -o "$dst" -j ACCEPT -m comment --comment "$cmt" 2>/dev/null; then
    iptables -A FORWARD -i "$src" -o "$dst" -j ACCEPT -m comment --comment "$cmt"
    ok "FORWARD: $src -> $dst ACCEPT"
  else
    ok "FORWARD: $src -> $dst already present"
  fi
}

ensure_forward "$ZT_IF"  "$LAN_IF" "zt-lan-out"
ensure_forward "$LAN_IF" "$ZT_IF"  "zt-lan-in"

# conntrack/established already covered by INPUT/FORWARD policy ACCEPT or
# by the system-wide conntrack rule. If your FORWARD policy is DROP, the
# return path is already allowed by the conntrack ESTABLISHED,RELATED rule
# (added below if missing).
if ! iptables -C FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null; then
  iptables -I FORWARD 1 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT \
    -m comment --comment "zt-lan-conntrack"
  ok "FORWARD: added ESTABLISHED,RELATED accept"
else
  ok "FORWARD: ESTABLISHED,RELATED already present"
fi

if ! iptables -t nat -C POSTROUTING -s "$ZT_NET" -o "$LAN_IF" -j MASQUERADE 2>/dev/null; then
  iptables -t nat -A POSTROUTING -s "$ZT_NET" -o "$LAN_IF" -j MASQUERADE \
    -m comment --comment "zt-lan-masq"
  ok "NAT: $ZT_NET -> $LAN_IF MASQUERADE"
else
  ok "NAT: masquerade already present"
fi

# --- 3. Persist iptables ---
bold "[3/5] Persist iptables rules"
if ! dpkg -s iptables-persistent >/dev/null 2>&1; then
  warn "iptables-persistent not installed. Installing (non-interactive)..."
  DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent >/dev/null
  ok "Installed iptables-persistent"
else
  ok "iptables-persistent already installed"
fi
iptables-save > /etc/iptables/rules.v4
ok "Saved to /etc/iptables/rules.v4"

# --- 4. Boot-time idempotency unit (belt + suspenders) ---
bold "[4/5] Systemd unit: re-apply rules on boot (idempotent)"
UNIT=/etc/systemd/system/zt-lan-route.service
cat > "$UNIT" <<EOF
[Unit]
Description=Apply ZeroTier <-> LAN iptables rules at boot
After=network-online.target zerotier-one.service
Wants=network-online.target
Before=network-pre.target

[Service]
Type=oneshot
RemainAfterExit=yes
# Re-run the setup script; every step is idempotent.
ExecStart=/bin/bash /home/pi/.openclaw/workspace/scripts/zt-lan-route-setup.sh

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable zt-lan-route.service
ok "Enabled $UNIT"

# --- 5. Verify ---
bold "[5/5] Verify"
echo "  ip_forward:  $(sysctl -n net.ipv4.ip_forward)"
echo "  ZT addr:     $(ip -4 -br addr show $ZT_IF | awk '{print $3}')"
echo "  LAN addr:    $(ip -4 -br addr show $LAN_IF | awk '{print $3}')"
echo
echo "FORWARD chain (zerotier-related):"
iptables -S FORWARD | grep -E 'zt-lan|conntrack.*ESTABLISHED' || true
echo
echo "NAT chain (zerotier-related):"
iptables -t nat -S POSTROUTING | grep zt-lan || true
echo
bold "DONE"
echo
echo "NEXT STEP (you, on https://my.zerotier.com -> your network -> Rules):"
echo "  Add a single flow rule (or merge with your existing accept-all):"
echo "    accept ip saddr 10.59.0.0/16 daddr 192.168.1.0/24"
echo "    accept ip saddr 192.168.1.0/24 daddr 10.59.0.0/16"
echo
echo "If your current rules are 'drop; accept; ' (default), insert these BEFORE"
echo "the 'accept;' (rules are first-match-wins)."
echo
echo "Then from any ZeroTier peer (laptop, phone, etc.):"
echo "  ssh pi@192.168.1.162          # the sbitx box, via the Pi as gateway"
echo "  ssh pi@192.168.1.147          # the Pi itself (also works via its ZT IP)"
