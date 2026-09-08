#!/bin/bash
# collect-box-status.sh — report the actual state of this g90 box.
#
# Output: JSON on stdout, one line per top-level key. Suitable for
# /api/v1/box-status on the launcher Flask app.
#
# Idempotent. Fast (<2s). Read-only. No sudo required.
#
# What it reports:
#   launcher_version   — `git describe --tags --abbrev=0` in $LAUNCHER_DIR,
#                        or "image-baked" if not a working tree,
#                        or "missing" if the directory isn't there.
#   systemd_units      — array of {name, state} for the units the manifest
#                        lists. "missing" if the unit file isn't installed.
#   pip_packages       — array of {venv, packages} where packages is a
#                        comma-separated name==version string from `pip list`.
#   config_files       — array of {path, exists, mode} for the files the
#                        manifest lists.
#
# Required env:
#   LAUNCHER_DIR  — path to the launcher working tree (default /home/pi/shared_launcher)
#   PIPX_HOME     — pipx install root (default /home/pi/.local)

set -euo pipefail

LAUNCHER_DIR="${LAUNCHER_DIR:-/home/pi/shared_launcher}"
PIPX_HOME="${PIPX_HOME:-/home/pi/.local}"

# --- launcher version ---------------------------------------------------------

if [ ! -d "$LAUNCHER_DIR" ]; then
    launcher_version='"missing"'
elif [ -d "$LAUNCHER_DIR/.git" ]; then
    ver=$(cd "$LAUNCHER_DIR" && git describe --tags --abbrev=0 2>/dev/null || echo unknown)
    launcher_version="\"$ver\""
else
    launcher_version='"image-baked"'
fi

# --- systemd units ------------------------------------------------------------

units_json=""
for u in g90-shared-launcher reticulumhf-rnsd meshchatx modem73 lxmd; do
    state=$(systemctl is-active "${u}.service" 2>/dev/null || echo missing)
    units_json="${units_json}{\"name\":\"${u}\",\"state\":\"${state}\"},"
done
units_json="${units_json%,}"

# --- pip packages (per venv) --------------------------------------------------

pip_json=""
for v in rns reticulum-meshchatx; do
    pip_bin="${PIPX_HOME}/pipx/venvs/${v}/bin/pip"
    if [ -x "$pip_bin" ]; then
        pkgs=$("$pip_bin" list --format=freeze 2>/dev/null \
            | awk -F'==' '{printf "%s==%s,", $1, $2}' \
            | sed 's/,$//')
        pip_json="${pip_json}{\"venv\":\"${v}\",\"packages\":\"${pkgs}\"},"
    else
        pip_json="${pip_json}{\"venv\":\"${v}\",\"packages\":\"\"},"
    fi
done
pip_json="${pip_json%,}"

# --- config files -------------------------------------------------------------

files_json=""
for f in \
    /home/pi/.reticulum/config \
    /etc/systemd/system/modem73.service \
    /etc/systemd/system/meshchatx.service \
    /usr/local/bin/restart-meshchatx
do
    if [ -e "$f" ]; then
        mode=$(stat -c '%a' "$f" 2>/dev/null || echo "?")
        files_json="${files_json}{\"path\":\"${f}\",\"exists\":true,\"mode\":\"${mode}\"},"
    else
        files_json="${files_json}{\"path\":\"${f}\",\"exists\":false},"
    fi
done
files_json="${files_json%,}"

# --- emit JSON ----------------------------------------------------------------

cat <<JSON
{"launcher_version":${launcher_version},"systemd_units":[${units_json}],"pip_packages":[${pip_json}],"config_files":[${files_json}]}
JSON
