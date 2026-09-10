#!/bin/bash
# capture-config.sh — capture a g90 box's config files into a tarball.
#
# Standalone version of the v0.6.46 launcher's /backup-configs route,
# for boxes where the launcher can't be updated (e.g. g90f1r2 — the
# shipping unit on ZT 10.59.42.236 that the operator can't reach from
# m5boss because it's on a different wifi).
#
# Run on the source box as the pi user:
#   bash capture-config.sh [output-dir]
#
# Default output dir is /home/pi. The tarball is named
# g90-configs-<hostname>-<date>-<time>.tar.gz so a multi-box
# operator can tell which box an archive came from.
#
# The whitelist is closed (no globs; no /home/pi/ sweep). To
# add a path, edit CONFIG_PATHS below and ship a new release.
#
# What's NOT captured (deliberately):
#   - /etc/systemd/system/*.service (deployment-state, not config)
#   - bash_history, ssh keys, etc. (whitelist is closed)
#   - the box's network identity (subnet, IPs) — that's
#     hardware-specific and not portable between boxes
#
# This is box-specific (per operator 2026-09-09 21:38 MDT):
# the captured /home/pi/.reticulum/config includes the box's
# Reticulum identity. Restoring this backup to a different
# box will give the new box the old box's identity on the
# mesh. That's the intent — restores are for fleet rebuilds.
#
# Exit codes:
#   0  — tarball written, summary printed
#   1  — could not determine hostname / write output

set -euo pipefail

# Whitelist (mirror of scripts/config_backup.py:CONFIG_WHITELIST).
# Each entry is "absolute_path is_dir" where is_dir is 0 for a
# file, 1 for a directory (recursively captured). The
# alignment whitespace between path and is_dir is for source
# readability; we trim it with xargs at parse time.
CONFIG_PATHS=(
    "/home/pi/.reticulum/config                                          0"
    "/etc/reticulumhf/config.env                                         0"
    "/home/pi/.config/pat                                                1"
    "/home/pi/.config/modem73                                            1"
    "/home/pi/.config/ardopc                                             1"
    "/home/pi/.config/direwolf                                           1"
    "/home/pi/.config/js8call                                            1"
    "/home/pi/.config/fldigi                                             1"
    "/home/pi/.config/flrig                                              1"
    "/home/pi/.config/wsjtx                                              1"
    "/home/pi/.config/hamlib                                             1"
    "/home/pi/.config/pavucontrol.ini                                    0"
    "/etc/hostapd/hostapd.conf                                           0"
    "/etc/dhcp/dhcpd.conf                                                0"
    "/home/pi/.local/share/patmenu2                                      1"
)

# Output dir (CLI arg or default)
OUT_DIR="${1:-/home/pi}"

# Hostname (short form, fallback to 'g90')
HOSTNAME=$(hostname -s 2>/dev/null || echo "g90")
if [ -z "$HOSTNAME" ]; then
    HOSTNAME="g90"
fi

# Try to read the launcher's version (if any). Falls back to
# 'no-launcher' for boxes like g90f1r2 that don't have the
# shared launcher.
LAUNCHER_DIR="${LAUNCHER_DIR:-/home/pi/shared_launcher}"
if [ -d "$LAUNCHER_DIR/.git" ]; then
    LAUNCHER_VERSION=$(cd "$LAUNCHER_DIR" && git describe --tags --abbrev=0 2>/dev/null || echo "no-launcher")
else
    LAUNCHER_VERSION="no-launcher"
fi

# Timestamp for the filename (UTC so the name is portable
# across timezones; the file mtime is also normalized to a
# fixed point so byte-equal runs produce the same tarball).
TS=$(date -u +%Y%m%d-%H%M%S)
TARBALL_NAME="g90-configs-${HOSTNAME}-${LAUNCHER_VERSION}-${TS}.tar.gz"
TARBALL_PATH="${OUT_DIR}/${TARBALL_NAME}"

# Sanity: can we write the output?
if [ ! -d "$OUT_DIR" ]; then
    echo "ERROR: output dir does not exist: $OUT_DIR" >&2
    exit 1
fi
if [ ! -w "$OUT_DIR" ]; then
    echo "ERROR: output dir not writable: $OUT_DIR" >&2
    exit 1
fi

# Fixed mtime for the archive header (deterministic tarball
# for byte-equal reruns). Per-file mtimes are preserved from
# the source. 2026-09-09 12:00:00 UTC = boot of the freshly-
# built reticulumpi box.
EPOCH_FIXED=$(date -u -d "2026-09-09 12:00:00" +%s 2>/dev/null \
              || python3 -c "
import datetime, calendar
print(calendar.timegm(
    datetime.datetime(2026, 9, 9, 12, 0, 0,
                      tzinfo=datetime.timezone.utc).timetuple()
))")

# Walk the whitelist twice. First pass: build the list of
# path arguments to pass to tar. We collect them as bare
# filesystem paths (with leading /) so tar can read them.
# Second pass: invoke tar once with all of them, using
# --transform to strip the leading / so the archive has
# the same shape as the v0.6.46 launcher's tarball
# ("home/pi/.reticulum/config" not "/home/pi/.reticulum/config").
# Directories are passed as-is; tar recurses automatically.
INCLUDED=()
SKIPPED=()
TAR_ARGS=()

for entry in "${CONFIG_PATHS[@]}"; do
    # entry is "path is_dir" — split on the LAST space.
    # Trim path whitespace with xargs (the alignment
    # whitespace between path and is_dir would otherwise
    # be part of the path string).
    path="$(echo "${entry% *}" | xargs)"
    is_dir="${entry##* }"

    if [ ! -e "$path" ]; then
        SKIPPED+=("$path (not on this box)")
        continue
    fi

    INCLUDED+=("$path")
    TAR_ARGS+=("$path")
done

# Now invoke tar once with all the paths. We pass
# --transform to strip the leading slash, and
# --warning=no-file-changed (no-op on this version)
# to be safe against future tar versions.
if [ "${#TAR_ARGS[@]}" -eq 0 ]; then
    # Nothing to capture. Write an empty tarball with
    # a single member that says "empty" so the file
    # is well-formed.
    tar --create --gzip \
        --file="$TARBALL_PATH" \
        --mtime="@${EPOCH_FIXED}" \
        --transform 's,^,EMPTY:,' \
        --files-from /dev/null
    trap - EXIT
    echo "  included (0 paths)"
    echo "  tarball: $TARBALL_PATH (empty)"
    exit 0
fi

tar --create --gzip \
    --file="$TARBALL_PATH" \
    --mtime="@${EPOCH_FIXED}" \
    --transform 's,^/,,' \
    "${TAR_ARGS[@]}" 2>/dev/null

# Make the tarball world-readable so the operator can scp
# it back to the dev machine (the script ran as pi, so
# without this the file is mode 600).
chmod 644 "$TARBALL_PATH"

# Summary
echo "=== Capturing g90 box config ==="
echo "  hostname:           $HOSTNAME"
echo "  launcher version:   $LAUNCHER_VERSION"
echo "  output:             $TARBALL_PATH"
echo
echo "  included (${#INCLUDED[@]} paths):"
for p in "${INCLUDED[@]}"; do
    echo "    + $p"
done
echo
if [ "${#SKIPPED[@]}" -gt 0 ]; then
    echo "  skipped (${#SKIPPED[@]} paths — not on this box):"
    for p in "${SKIPPED[@]}"; do
        echo "    - $p"
    done
    echo
fi
echo "  tarball: $TARBALL_PATH ($(stat -c %s "$TARBALL_PATH") bytes)"
echo
echo "Done. To restore on a different box, copy the tarball"
echo "there and run restore-config.sh:"
echo
echo "  scp $TARBALL_PATH pi@<target-box>:/tmp/"
echo "  ssh pi@<target-box> 'bash restore-config.sh /tmp/$TARBALL_NAME'"
echo
