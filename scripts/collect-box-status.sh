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

# Use python to build the JSON so we get proper string escaping for free.
python3 - "$LAUNCHER_DIR" "$PIPX_HOME" << 'PYEOF'
import json
import os
import subprocess
import sys

launcher_dir = sys.argv[1]
pipx_home = sys.argv[2]

# --- launcher version ---------------------------------------------------------

if not os.path.isdir(launcher_dir):
    launcher_version = "missing"
elif os.path.isdir(os.path.join(launcher_dir, ".git")):
    try:
        launcher_version = subprocess.run(
            ["git", "-C", launcher_dir, "describe", "--tags", "--abbrev=0"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip().replace("^{}", "") or "untagged"
    except Exception:
        launcher_version = "unknown"
else:
    launcher_version = "image-baked"

# --- systemd units ------------------------------------------------------------

# Use `systemctl show -p ActiveState --value` which guarantees a single
# token on stdout. `systemctl is-active` can return multi-line output
# (e.g. "inactive\nmissing") when the unit is in a transitional state,
# which breaks naive JSON consumers.
units = []
for u in ["g90-shared-launcher", "reticulumhf-rnsd", "meshchatx", "modem73", "lxmd"]:
    try:
        state = subprocess.run(
            ["systemctl", "show", f"{u}.service", "-p", "ActiveState", "--value"],
            capture_output=True, text=True, timeout=3
        ).stdout.strip()
        if not state:
            state = "missing"
    except Exception:
        state = "unknown"
    units.append({"name": u, "state": state})

# --- pip packages (per venv) --------------------------------------------------

# pipx venvs on this image don't ship a `pip` binary in bin/ — only the
# entry-point scripts (rnsd, lxmd, meshchatx, etc). pip must be invoked via
# the venv's python interpreter as `python -m pip`.
pkgs_by_venv = []
for v in ["rns", "reticulum-meshchatx"]:
    py_bin = os.path.join(pipx_home, "pipx", "venvs", v, "bin", "python")
    pkgs = []
    if os.path.isfile(py_bin):
        try:
            out = subprocess.run(
                [py_bin, "-m", "pip", "list", "--format=freeze"],
                capture_output=True, text=True, timeout=10
            ).stdout
            for line in out.splitlines():
                if "==" in line:
                    name, ver = line.split("==", 1)
                    pkgs.append(f"{name}=={ver}")
        except Exception:
            pass
    pkgs_by_venv.append({"venv": v, "packages": ",".join(pkgs)})

# --- config files -------------------------------------------------------------

files = []
for f in [
    "/home/pi/.reticulum/config",
    "/etc/systemd/system/modem73.service",
    "/etc/systemd/system/meshchatx.service",
    "/usr/local/bin/restart-meshchatx",
]:
    if os.path.exists(f):
        try:
            mode = oct(os.stat(f).st_mode & 0o777)[2:]
        except Exception:
            mode = "?"
        files.append({"path": f, "exists": True, "mode": mode})
    else:
        files.append({"path": f, "exists": False})

# --- emit JSON ----------------------------------------------------------------

print(json.dumps({
    "launcher_version": launcher_version,
    "systemd_units": units,
    "pip_packages": pkgs_by_venv,
    "config_files": files,
}, indent=None))
PYEOF
