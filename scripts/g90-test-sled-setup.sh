#!/bin/bash
# g90-test-sled-setup.sh — install the test launcher service
#
# Run once after the work tree is in place at
# /media/pi/USB20FD/Working/g90-test-sled/work/.
#
# What it does:
#   1. Copies g90-test-launcher.service to /etc/systemd/system/
#   2. Adjusts the WorkingDirectory / ExecStart in the unit if the
#      work tree path ever moves
#   3. systemctl daemon-reload
#   4. systemctl enable --now g90-test-launcher.service
#   5. Prints the URL to open in a browser
#
# To uninstall: sudo systemctl disable --now g90-test-launcher.service
#   and rm /etc/systemd/system/g90-test-launcher.service

set -e
export SUDO_ASKPASS="/home/pi/.local/bin/askpass-g90.sh"
export SUDO_ASKPASS_REQUIRE=force

WORK="/media/pi/USB20FD/Working/g90-test-sled/work"
SERVICE_SRC="/home/pi/.openclaw/workspace/g90-test-launcher.service"
SERVICE_DST="/etc/systemd/system/g90-test-launcher.service"
LOGS="/home/pi/g90-test-sled/logs"

if [ ! -d "$WORK" ]; then
    echo "ERROR: $WORK does not exist. Clone the g90-launcher repo there first."
    exit 1
fi

if [ ! -f "$WORK/app.py" ]; then
    echo "ERROR: $WORK/app.py missing. The work tree is incomplete."
    exit 1
fi

# Make sure the log dir exists
mkdir -p "$LOGS"

# Install the service
sudo -A cp "$SERVICE_SRC" "$SERVICE_DST"
sudo -A chmod 644 "$SERVICE_DST"
sudo -A systemctl daemon-reload

# Start it (don't enable — this is a dev sled, not a long-running service)
sudo -A systemctl enable g90-test-launcher.service
sudo -A systemctl restart g90-test-launcher.service

sleep 2

echo
echo "=== g90 test sled installed ==="
echo
echo "Work tree:  $WORK"
echo "Service:    $SERVICE_DST"
echo "Logs:       /home/pi/g90-test-sled/logs/launcher.log"
echo
echo "URL:        http://$(hostname).local:9090/  (or http://127.0.0.1:9090/ from the Pi itself)"
echo
echo "--- service status ---"
sudo -A systemctl is-active g90-test-launcher.service
echo
echo "--- port check ---"
ss -tlnp 2>/dev/null | grep :9090 | head
echo
echo "To uninstall:"
echo "  sudo systemctl disable --now g90-test-launcher.service"
echo "  sudo rm $SERVICE_DST"
