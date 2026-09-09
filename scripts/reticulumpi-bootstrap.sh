#!/bin/bash
# reticulumpi-bootstrap.sh — build a working reticulumpi box from stock ReticulumHF.
#
# Run as the pi user on a freshly-flashed ReticulumHF-base Pi:
#   bash reticulumpi-bootstrap.sh
#
# The script is idempotent: re-running is safe. It does not overwrite
# operator-tweaked configs (/etc/reticulumhf/config.env, /etc/hostapd/
# hostapd.conf) — those are operator values, not bootstrap values.
#
# What it does, in order:
#   Phase 0: Sanity check (ReticulumHF base, network, disk space)
#   Phase 1: apt sources (add ZeroTier's download.zerotier.com repo)
#   Phase 2: apt install (system tools, radio apps, noVNC stack)
#   Phase 3: pipx (rns==1.4.2 + lxmf inject, freedvtnc2, reticulum-meshchatx)
#   Phase 4: github binaries (modem73 .deb pinned to 2.4.0)
#   Phase 5: pre-existing service directories (mkdir + chown)
#   Phase 6: clone reticulumpi + pin to latest github tag
#   Phase 7: overlay config + systemd units
#   Phase 8: x11vnc password (random 8 chars, printed once)
#   Phase 9: systemctl daemon-reload + enable --now
#   Phase 10: verify (curl /launcher-status, all components match)
#   Phase 11: prompt for ZeroTier network ID + join (optional)
#
# What's NOT in this script:
#   - Flashing the SD card (do that with Pi Imager first)
#   - First-boot setup wizard (ReticulumHF base's own wizard handles it)
#   - Operator-specific config (SSID, password, callsign, freqs)
#   - Image capture (use BUILD.md Step 8 after the build is verified)

set -euo pipefail

# ============================================================================
# Configuration
# ============================================================================

GITHUB_REPO="https://github.com/smeshT/reticulumpi.git"
GITHUB_RAW_BASE="https://raw.githubusercontent.com/smeshT/reticulumpi/main"
LAUNCHER_DIR="/home/pi/shared_launcher"
# Launcher on :80 to match the deployed g90 layout (port 80 is what
# the wifi captive portal redirects to; the launcher is the daily-
# driver UI). The ReticulumHF setup wizard sits on :8080.
# Override at run time: LAUNCHER_PORT=9090 bash reticulumpi-bootstrap.sh
LAUNCHER_PORT="${LAUNCHER_PORT:-80}"
MODEM73_VERSION="2.4.0"
RNS_VERSION="1.4.2"
LXMF_VERSION=""  # latest
FREEDVTNC2_VERSION=""  # latest
RETICULUM_MESHCHATX_VERSION=""  # latest

# ============================================================================
# PATH
# ============================================================================
# pi user's non-interactive shell has PATH=/usr/local/bin:/usr/bin:/bin:/usr/games
# — no /usr/sbin, /sbin, or /home/pi/.local/bin. Add them so 'command -v'
# finds binaries like avahi-daemon, zerotier-cli, AND pipx shims like lxmd.
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/home/pi/.local/bin"

# ============================================================================
# Pretty output
# ============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

phase() { echo -e "\n${BLUE}==[ $* ]==${NC}"; }
ok()    { echo -e "  ${GREEN}OK${NC}: $*"; }
warn()  { echo -e "  ${YELLOW}WARN${NC}: $*"; }
fail()  { echo -e "  ${RED}FAIL${NC}: $*" >&2; exit 1; }

# ============================================================================
# Phase 0: Sanity check
# ============================================================================

phase "Phase 0: Sanity check"

# Are we pi?
if [ "$(id -u)" -ne "$(id -u pi)" ] && [ "$(whoami)" != "pi" ]; then
    warn "not running as pi; some phases may fail. continue anyway."
fi

# Is this bookworm?
if ! grep -q 'bookworm' /etc/os-release 2>/dev/null; then
    fail "this script targets Debian 12 (bookworm). /etc/os-release does not say bookworm."
fi
ok "OS is bookworm"

# Architecture check
ARCH=$(uname -m)
[ "$ARCH" = "aarch64" ] || fail "this script targets aarch64 (Pi 4/5 64-bit); got '$ARCH'"
ok "arch is aarch64"

# Network up?
if ! ping -c1 -W2 deb.debian.org >/dev/null 2>&1; then
    fail "no network connectivity to deb.debian.org. check wifi/Ethernet."
fi
ok "network reachable"

# Disk space (need ~1 GB for apt + pipx venvs + image overlay)
ROOT_FREE_KB=$(df -k / | tail -1 | awk '{print $4}')
[ "$ROOT_FREE_KB" -gt 1048576 ] || fail "less than 1 GB free on /; got $((ROOT_FREE_KB / 1024)) MB"
ok "disk space: $((ROOT_FREE_KB / 1024)) MB free on /"

# ============================================================================
# Phase 1: apt sources
# ============================================================================

phase "Phase 1: Add ZeroTier apt source"

# Pre-seed dpkg answers (avoid modified-config prompts on initramfs-tools etc.)
export DEBIAN_FRONTEND=noninteractive

if [ ! -f /etc/apt/sources.list.d/zerotier.list ]; then
    curl -fsSL 'https://raw.githubusercontent.com/zerotier/ZeroTierOne/main/doc/contact%40zerotier.com.gpg' \
        | sudo gpg --dearmor -o /usr/share/keyrings/zerotier-archive-keyring.gpg
    echo 'deb [signed-by=/usr/share/keyrings/zerotier-archive-keyring.gpg] https://download.zerotier.com/debian/bookworm bookworm main' \
        | sudo tee /etc/apt/sources.list.d/zerotier.list
    ok "ZeroTier apt source added"
else
    ok "ZeroTier apt source already present"
fi

sudo apt update
ok "apt update succeeded"

# Verify zerotier is available
apt-cache policy zerotier-one > /tmp/zerotier-policy.txt 2>/dev/null
if ! grep -m1 -q "download.zerotier.com" /tmp/zerotier-policy.txt; then
    fail "zerotier-one not available from download.zerotier.com. check apt sources."
fi
ok "zerotier-one available from download.zerotier.com"

# ============================================================================
# Phase 2: apt install
# ============================================================================

phase "Phase 2: apt install (system tools, radio apps, noVNC stack)"

# Block 1: core tools + digimode apps + noVNC stack
sudo apt install -y \
    git curl wget xz-utils gpg ca-certificates \
    python3 python3-pip python3-venv \
    flrig fldigi js8call wsjtx pat \
    direwolf \
    avahi-daemon avahi-utils \
    xterm lxterminal pulseaudio pavucontrol \
    novnc python3-novnc python3-websockify websockify \
    x11vnc xvfb openbox \
    fonts-dejavu-core \
    libcap2-bin
ok "apt install block 1 (system tools, radio apps, noVNC stack) succeeded"

# Grant python3 the ability to bind to low ports (<1024). The shared
# launcher runs as User=pi but binds to :80 so wifi clients can land
# on it after the captive-portal redirect. Without cap_net_bind_service
# the bind fails with PermissionError [errno 13]. g90digi has this
# set via libcap2-bin's setcap; we apply the same here. (The
# cap_net_bind_service capability only applies to socket bind(),
# nothing else — it's the standard "let a non-root process bind
# privileged ports" pattern.)
PYTHON_BIN=$(readlink -f /usr/bin/python3)
sudo setcap cap_net_bind_service=+ep "$PYTHON_BIN"
ok "python3 granted cap_net_bind_service ($PYTHON_BIN)"

# Verify: every binary resolves
MISSING_BIN=0
for b in git curl wget xz gpg python3 pip flrig fldigi js8call wsjtx \
         pat-winlink direwolf avahi-daemon avahi-browse \
         xterm lxterminal pulseaudio pavucontrol \
         x11vnc websockify Xvfb openbox; do
    if ! command -v "$b" >/dev/null 2>&1; then
        warn "binary missing: $b"
        MISSING_BIN=$((MISSING_BIN + 1))
    fi
done
# novnc has no binary; check for the web UI directory
if [ ! -d /usr/share/novnc ]; then
    warn "directory missing: /usr/share/novnc"
    MISSING_BIN=$((MISSING_BIN + 1))
fi
[ "$MISSING_BIN" -eq 0 ] || fail "$MISSING_BIN binaries/files missing after install"
ok "all binaries present"

# Block 2: zerotier
if ! command -v zerotier-cli >/dev/null 2>&1; then
    sudo apt install -y zerotier-one
    sudo dpkg --configure -a 2>/dev/null || true  # postinst may have errored; finish it
fi
command -v zerotier-cli >/dev/null || fail "zerotier-cli still missing"
file /usr/sbin/zerotier-one | grep -q "ARM aarch64" || fail "zerotier-one is not aarch64"
ls -la /lib/systemd/system/zerotier-one.service >/dev/null || fail "zerotier-one.service not on disk"
ok "zerotier-one installed (binary + unit file)"

# Block 3: pipx
sudo apt install -y pipx
pipx ensurepath
ok "pipx installed"

# ============================================================================
# Phase 3: pipx venvs
# ============================================================================

phase "Phase 3: pipx venvs (Reticulum stack)"

# rns 1.4.2 — matches the manifest's min_version. ReticulumHF base ships rns
# 1.1.3, so we force-upgrade. This works for rns; do NOT try to upgrade
# reticulumhf-rnsd's bundled rns (it's pinned to 1.1.3 via the base image).
pipx install --force "rns==${RNS_VERSION}" 2>&1 | tail -3
/home/pi/.local/pipx/venvs/rns/bin/python -c "import RNS; assert RNS.__version__.split('.')[0:2] >= ['1','4'], f'rns {RNS.__version__} too old'" \
    || fail "rns version check failed"
ok "rns ${RNS_VERSION} installed"

# Two-step lxmf install:
# 1. pipx install lxmf — creates a standalone lxmd shim in
#    /home/pi/.local/bin/lxmd (the systemd unit lxmd.service uses this).
# 2. pipx inject rns lxmf — copies the LXMF package into the rns venv
#    so the launcher's component check (which does 'import LXMF' from
#    the rns venv's python) can find it.
#    NB: pipx inject does NOT create shim symlinks; that's why we
#    do BOTH steps.
pipx install lxmf 2>&1 | tail -3
pipx inject rns lxmf 2>&1 | tail -3
# lxmf installs as package 'lxmf' but the Python module is 'LXMF' (uppercase)
# — see site-packages/LXMF in the rns venv. Import the right name.
/home/pi/.local/pipx/venvs/rns/bin/python -c "import LXMF; print(f'lxmf {LXMF.__version__}')" \
    || fail "lxmf not in rns venv (pipx inject rns lxmf may have failed)"
command -v lxmd >/dev/null || fail "lxmd shim not on PATH (pipx install lxmf may have failed)"
ok "lxmf installed (lxmd shim + LXMF in rns venv)"

# Other venvs (separate, isolated)
pipx install freedvtnc2 2>&1 | tail -3
pipx install reticulum-meshchatx 2>&1 | tail -3
ok "freedvtnc2 + reticulum-meshchatx installed"

# Verify all binaries on PATH
# pipx package names vs console_script names:
#   - lxmf package -> lxmd binary
#   - freedvtnc2 package -> freedvtnc2 binary
#   - reticulum-meshchatx package -> meshchatx binary (not reticulum-meshchatx)
for b in lxmd freedvtnc2 meshchatx; do
    command -v "$b" >/dev/null || fail "$b not on PATH after pipx install"
done
ok "all pipx shims on PATH"

# ============================================================================
# Phase 4: github binaries (modem73)
# ============================================================================

phase "Phase 4: modem73 (github release .deb)"

if ! file /usr/bin/modem73 2>/dev/null | grep -q "ARM aarch64"; then
    MODEM73_DEB="modem73_${MODEM73_VERSION}_debian-12_arm64.deb"
    wget -q "${GITHUB_RAW_BASE}/../../../RFnexus/modem73/releases/download/v${MODEM73_VERSION}/${MODEM73_DEB}" \
        -O "/tmp/${MODEM73_DEB}" 2>/dev/null || \
        wget -q "https://github.com/RFnexus/modem73/releases/download/v${MODEM73_VERSION}/${MODEM73_DEB}" \
            -O "/tmp/${MODEM73_DEB}"
    sudo apt install -y "/tmp/${MODEM73_DEB}"
    rm -f "/tmp/${MODEM73_DEB}"
fi
file /usr/bin/modem73 | grep -q "ARM aarch64" || fail "modem73 binary not aarch64"
ok "modem73 ${MODEM73_VERSION} installed"

# ============================================================================
# Phase 5: pre-existing service directories
# ============================================================================

phase "Phase 5: pre-existing service directories"

# The launcher's component check, meshchatx, and lxmd all need their
# runtime directories to exist BEFORE the units start. ProtectSystem=strict
# + ReadWritePaths= requires dirs to pre-exist.
sudo mkdir -p /home/pi/.config/pat
sudo chown pi:pi /home/pi/.config/pat
ok "/home/pi/.config/pat"

sudo mkdir -p /home/pi/.reticulum
sudo chown pi:pi /home/pi/.reticulum
ok "/home/pi/.reticulum"

# Add the [[Modem73]] Reticulum interface block to the config if it
# doesn't exist. The ReticulumHF wizard writes the config without this
# block; without it, the launcher's toggle_modem73_audio.sh can't
# enable the modem73 OFDM bearer and the button silently fails. We
# create the block here so the button works on first run. Pattern
# matches g90digi's config: type=Modem73Interface, target_port=8002,
# control_port=8073, mode=roaming (rate-limits per-interface
# announces; full internal mode causes cross-box announce cascades).
if [ ! -f /home/pi/.reticulum/config ] || ! grep -qi '^\s*\[\[Modem73\]\]' /home/pi/.reticulum/config; then
    RETICULUM_CONFIG=/home/pi/.reticulum/config
    if [ -f "$RETICULUM_CONFIG" ]; then
        # Config exists but no Modem73 block — append.
        sudo -u pi bash -c "cat >> '$RETICULUM_CONFIG' <<'EOF'

[[Modem73]]
  type = Modem73Interface
  enabled = false
  target_host = 127.0.0.1
  target_port = 8002
  control_host = 127.0.0.1
  control_port = 8073
  mode = roaming
  announce_cap = 1
EOF"
        ok "appended [[Modem73]] block to existing Reticulum config"
    fi
    # If the config doesn't exist yet, the ReticulumHF wizard will
    # create it on first run; the toggle script's case-insensitive
    # fallback will add the Modem73 block on the first toggle.
fi

sudo mkdir -p /home/pi/.lxmd
sudo chown pi:pi /home/pi/.lxmd
ok "/home/pi/.lxmd"

# ============================================================================
# Phase 6: clone reticulumpi + pin to latest
# ============================================================================

phase "Phase 6: clone reticulumpi + pin to latest"

if [ ! -d "$LAUNCHER_DIR" ]; then
    git clone "$GITHUB_REPO" "$LAUNCHER_DIR"
    ok "cloned $GITHUB_REPO -> $LAUNCHER_DIR"
else
    ok "shared_launcher already cloned"
fi

cd "$LAUNCHER_DIR"
git fetch --tags

# Get latest tag from github
# Filter to only vX.Y.Z tags (3-segment). 'git ls-remote --sort=-v:refname'
# returns v0.6 BEFORE v0.6.28 because 'v0.6' is treated as 'v0.6.0' and
# the version comparison puts v0.6.0 > v0.6.28. Filtering to 3-segment
# tags avoids that. 'sed -n s/.*refs\/tags\///p' strips the SHA prefix
# from the line, leaving just the tag name.
LATEST_TAG=$(git ls-remote --tags --sort=-v:refname "$GITHUB_REPO" 2>/dev/null \
    | awk '/refs\/tags\/v[0-9]+\.[0-9]+\.[0-9]+$/ {print $2}' \
    | head -1 | sed 's|refs/tags/||; s/\^{}//')
if [ -z "$LATEST_TAG" ]; then
    fail "could not determine latest tag from github"
fi
ok "latest tag: $LATEST_TAG"

git checkout -f "$LATEST_TAG"
PINNED_SHA=$(git rev-parse HEAD)
ok "pinned to $LATEST_TAG ($PINNED_SHA)"

# ============================================================================
# Phase 7: overlay config + systemd units
# ============================================================================

phase "Phase 7: overlay (config files + systemd units)"

# Config files
sudo cp g90-image/config/reticulumhf-config.env /etc/reticulumhf/config.env

# Mark setup as complete. The ReticulumHF wizard creates this file
# when its setup flow finishes. If the operator prefers the bootstrap's
# defaults and wants freedvtnc2.service to actually start (its systemd
# unit has ConditionPathExists=!file), we create the file here. Delete
# it to re-run the wizard:
#   sudo rm /etc/reticulumhf/.setup_complete
sudo touch /etc/reticulumhf/.setup_complete

# Patch the ReticulumHF setup-portal to read PORT from the environment.
# Upstream the wizard hardcodes port 80 in /opt/reticulumhf/setup-portal/
# app.py:1799 ("app.run(host='0.0.0.0', port=80, debug=False)"), which
# conflicts with the launcher on :80. g90digi hand-patches this line to
# read os.environ.get('PORT', 8080) and binds 8080. We do the same
# patch here so the layout matches g90digi (launcher :80, wizard :8080,
# node-portal :8081).
WIZARD_APP=/opt/reticulumhf/setup-portal/app.py
if [ -f "$WIZARD_APP" ] && ! grep -q 'os.environ.get..PORT' "$WIZARD_APP"; then
    sudo sed -i 's|app.run(host="0.0.0.0", port=80, debug=False)|port=int(os.environ.get("PORT", 8080))\n    app.run(host="0.0.0.0", port=port, debug=False)|' "$WIZARD_APP"
    ok "patched wizard to read PORT from env (default 8080)"
elif [ -f "$WIZARD_APP" ]; then
    ok "wizard already reads PORT from env (no patch needed)"
else
    ok "wizard app.py not at $WIZARD_APP (ReticulumHF base not installed?)"
fi

# Set the wizard's PORT to 8080 in its systemd unit. The patch above
# only changes the app; we still need the unit to export PORT=8080.
sudo mkdir -p /etc/systemd/system/reticulumhf-portal.service.d
sudo tee /etc/systemd/system/reticulumhf-portal.service.d/port.conf >/dev/null <<'EOF'
[Service]
Environment="PORT=8080"
EOF
sudo systemctl daemon-reload
ok "wizard bound to :8080 (PORT=8080 in drop-in)"

sudo cp g90-image/config/hostapd.conf /etc/hostapd/hostapd.conf
sudo cp g90-image/config/pat-config.json /home/pi/.config/pat/config.json

# Node-portal (the wifi admin / app help UI on :8081). The overlay
# has g90-image/node-portal/app.py + g90-image/node-portal-templates/
# (apps.html, index.html, wifi.html). On g90digi this lives at
# /home/pi/node-portal/ with a /usr/local/bin/start-node-portal
# wrapper that exports PORT=8081. Without this install, the Wifi
# button + app help links in the launcher 404. Found missing
# 2026-09-09 15:53 MDT.
sudo install -d -o pi -g pi /home/pi/node-portal/templates
sudo install -o pi -g pi -m 0644 g90-image/node-portal/app.py /home/pi/node-portal/app.py
sudo install -o pi -g pi -m 0644 g90-image/node-portal-templates/*.html /home/pi/node-portal/templates/

# Wrapper: start-node-portal exports PORT=8081 then execs the app.
# (Pattern matches g90digi's wrapper exactly.)
sudo tee /usr/local/bin/start-node-portal >/dev/null <<'EOF'
#!/bin/bash
export PORT=8081
exec /usr/bin/python3 /home/pi/node-portal/app.py
EOF
sudo chmod +x /usr/local/bin/start-node-portal
ok "node-portal installed at /home/pi/node-portal/ (templates + wrapper)"

# Systemd unit for node-portal. Mirrors the g90digi layout: User=pi,
# ExecStart is the wrapper, Restart=always, no cap needed because
# PORT=8081 is unprivileged.
sudo tee /etc/systemd/system/node-portal.service >/dev/null <<'EOF'
[Unit]
Description=ReticulumHF Node Portal
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/node-portal
ExecStart=/usr/local/bin/start-node-portal
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now node-portal.service
ok "node-portal.service enabled + started"

# modem73 default settings (audio=0 so modem73 starts on any hardware).
# Only written if the file doesn't exist — operator's TUI-edited settings
# are never overwritten by the bootstrap.
if [ ! -f /home/pi/.config/modem73/settings ]; then
    sudo install -o pi -g pi -m 0644 \
        g90-image/config/modem73-default-settings \
        /home/pi/.config/modem73/settings
    ok "modem73 default settings installed (audio=0 for any-hardware start)"
else
    ok "modem73 settings already present, leaving alone"
fi

ok "config files copied"

# Sysctl: node-portal needs CAP_NET_BIND_SERVICE for :80
# (it's in the launcher's existing setup; ReticulumHF base handles it)

# Systemd units
for unit in g90-shared-launcher.service meshchatx.service lxmd.service \
            pat-http.service novnc-session.service zerotier-one.service; do
    if [ -f "g90-image/systemd-units/$unit" ]; then
        sudo cp "g90-image/systemd-units/$unit" /etc/systemd/system/
    fi
done
# restart-meshchatx is a binary, not a unit
if [ -f g90-image/systemd-units/restart-meshchatx ]; then
    sudo cp g90-image/systemd-units/restart-meshchatx /usr/local/bin/
    sudo chmod +x /usr/local/bin/restart-meshchatx
fi
ok "systemd units + binary copied"

# start-novnc-session script (different path — pi's local bin)
mkdir -p /home/pi/.local/bin
cp g90-image/config/start-novnc-session /home/pi/.local/bin/start-novnc-session
chmod +x /home/pi/.local/bin/start-novnc-session
ok "start-novnc-session script installed"

# noVNC password: NO LONGER SET (per operator 2026-09-09 15:14 MDT).
# The random 8-char password the bootstrap used to generate was hostile
# to the operator's browser-stored password (every re-run broke login),
# and provided no real security — anyone with LAN access can already
# pwn the Pi. The start-novnc-session script runs x11vnc WITHOUT
# -rfbauth, so noVNC is open. The hostapd WPA2 password on the wifi
# client portal is the only network-level auth that matters.
#
# If you want a VNC password back, uncomment the block below.
#
# sudo mkdir -p /etc/x11vnc
# head -c 64 /dev/urandom > /tmp/.novnc-pw.buf
# NOVNC_PASSWORD=*** -dc 'A-Za-z0-9' < /tmp/.novnc-pw.buf | head -c 8)
# sudo x11vnc -storepasswd "$NOVNC_PASSWORD" /etc/x11vnc/passwd
# sudo chmod 600 /etc/x11vnc/passwd
# sudo chown pi:pi /etc/x11vnc/passwd
# ok "x11vnc password file created (8 random chars: $NOVNC_PASSWORD)"
ok "noVNC password disabled (LAN-only security model)"

# ============================================================================
# Phase 8: prepare-* helpers
# ============================================================================

phase "Phase 8: prepare-* helpers (mkdir + chown for protected paths)"

for helper in g90-image/scripts/prepare-meshchatx-dirs.sh \
              g90-image/scripts/prepare-lxmd-dirs.sh; do
    if [ -f "$helper" ]; then
        sudo bash "$helper"
    fi
done
ok "prepare-* helpers ran"

# ============================================================================
# Phase 9: systemctl enable + start
# ============================================================================

phase "Phase 9: systemctl daemon-reload + enable --now"

sudo systemctl daemon-reload
ok "daemon-reload"

# Our overlay services
for svc in g90-shared-launcher.service \
           meshchatx.service \
           lxmd.service \
           pat-http.service \
           novnc-session.service \
           zerotier-one.service; do
    if sudo systemctl list-unit-files "$svc" >/dev/null 2>&1; then
        sudo systemctl enable --now "$svc" 2>&1 | tail -2
    else
        warn "unit file not found: $svc (skipping)"
    fi
done

# IMPORTANT: restart g90-shared-launcher so it picks up the overlay app.py
# from this git checkout. systemd starts the service with whatever code
# was on disk at boot, but we just did a fresh clone + checkout, so the
# currently-running process is from before.
sudo systemctl restart g90-shared-launcher.service
ok "g90-shared-launcher restarted"

# Wait for the services to settle
sleep 3

# ============================================================================
# Phase 10: verify
# ============================================================================

phase "Phase 10: verify (curl /launcher-status, all components match)"

# Service active check
for svc in g90-shared-launcher.service meshchatx.service lxmd.service \
           pat-http.service novnc-session.service zerotier-one.service; do
    state=$(systemctl is-active "$svc" 2>&1)
    if [ "$state" = "active" ]; then
        ok "$svc: active"
    else
        warn "$svc: $state"
    fi
done

# The launcher endpoint
sleep 2
echo
echo "--- /launcher-status ---"
LAUNCHER_STATUS=$(curl -sf "http://localhost:${LAUNCHER_PORT}/launcher-status" || echo "FAILED")
echo "$LAUNCHER_STATUS" | head -25
echo

echo "$LAUNCHER_STATUS" > /tmp/launcher-status.txt
if grep -m1 -q "All components match" /tmp/launcher-status.txt; then
    ok "launcher reports all components match"
elif grep -m1 -q "v0\." /tmp/launcher-status.txt; then
    warn "launcher is up but not all components match (see above)"
    echo
    echo "Common causes:"
    echo "  - reticulumhf-rnsd.service not active (ReticulumHF base issue)"
    echo "  - pip package version below min_version (check pipx list)"
    echo "  - meshchatx binary missing (apt install pipx package)"
    exit 1
else
    fail "launcher didn't return a valid /launcher-status"
fi

# noVNC endpoint
echo
echo "--- noVNC (port 6080) ---"
NOVNC_HEADERS=$(curl -sI "http://localhost:6080/" 2>&1 || echo "FAILED")
echo "$NOVNC_HEADERS" | head -3
echo "$NOVNC_HEADERS" > /tmp/novnc-headers.txt
if grep -m1 -q "WebSockify" /tmp/novnc-headers.txt; then
    ok "noVNC web UI responding"
else
    warn "noVNC web UI not responding on :6080"
fi

# ============================================================================
# Phase 11: ZeroTier join (optional)
# ============================================================================

phase "Phase 11: ZeroTier join (optional)"

sudo zerotier-cli status 2>&1 > /tmp/zt-status.txt
if grep -m1 -q "ONLINE" /tmp/zt-status.txt; then
    ok "zerotier-one is ONLINE"
    CURRENT_NWID=$(sudo zerotier-cli listnetworks 2>&1 | head -1 | awk '{print $3}')
    if [ -n "$CURRENT_NWID" ] && [ "$CURRENT_NWID" != "200" ]; then
        ok "joined network: $CURRENT_NWID"
    else
        echo
        read -p "Enter ZeroTier network ID to join (or Enter to skip): " ZT_NETWORK_ID
        if [ -n "$ZT_NETWORK_ID" ]; then
            sudo zerotier-cli join "$ZT_NETWORK_ID"
            ok "joined $ZT_NETWORK_ID — approve in your ZT central controller"
        else
            warn "skipped ZeroTier join. run 'sudo zerotier-cli join <nwid>' later."
        fi
    fi
else
    warn "zerotier-one is not online; skipping join"
fi

# ============================================================================
# Final summary
# ============================================================================

echo
echo "=========================================="
echo "reticulumpi-bootstrap complete."
echo "=========================================="
echo
echo "Launcher:    http://<lan-ip>:${LAUNCHER_PORT}/"
echo "             http://<lan-ip>:${LAUNCHER_PORT}/launcher-status"
echo "noVNC tab:   http://<lan-ip>:6080/vnc.html   (no password — LAN-only)"
echo
echo "Overlay version: ${LATEST_TAG} (${PINNED_SHA})"
echo
echo "Next steps:"
echo "  1. Edit /etc/reticulumhf/config.env — set RETICULUMHF_AP_SSID, _PASS,"
echo "     RADIO_ID, SERIAL_PORT, AUDIO_CARD for your deployment."
echo "  2. Edit /etc/hostapd/hostapd.conf — if you want a different SSID/channel."
echo "  3. Edit ~/.config/pat/config.json — set your callsign (NOT N0CALL)."
echo "  4. Reboot: sudo reboot"
echo "  5. Verify from your laptop:"
echo "       http://<lan-ip>:${LAUNCHER_PORT}/launcher-status   (should show 'All components match')"
echo "       http://<lan-ip>:6080/vnc.html                     (no password)"
echo
echo "If anything is broken, see BUILD.md Step 7's verification table."
