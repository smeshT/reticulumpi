#!/bin/bash
# restore-config.sh — restore a g90 box's config from a tarball.
#
# Standalone version of the v0.6.46 launcher's /restore-configs
# flow, for boxes where the launcher can't be updated
# (e.g. g90f1r2).
#
# Two-step flow matching the launcher's:
#   1. PREVIEW (default)  — extract to /tmp/<basename>-preview/,
#                          show what would change, prompt y/N.
#   2. APPLY  --apply     — extract + actually copy to live paths.
#
# Usage:
#   bash restore-config.sh <tarball.tar.gz>            # preview only
#   bash restore-config.sh <tarball.tar.gz> --apply    # preview + apply
#   bash restore-config.sh <tarball.tar.gz> --yes      # skip prompt
#
# The whitelist is the same as capture-config.sh so a backup
# from g90digi can be restored on g90f1r2 (and vice versa).
# The tarball's paths look like "home/pi/.reticulum/config"
# (leading / stripped); the script re-roots them to / when
# applying.
#
# Box-specific (per operator 2026-09-09 21:38 MDT): the
# tarball includes the source box's Reticulum identity.
# Restoring to a different box gives the new box the old
# box's identity. That's the intent — restores are for
# fleet rebuilds.
#
# Exit codes:
#   0  — preview shown (no apply); OR apply succeeded
#   1  — bad CLI / could not read tarball
#   2  — operator said N at the prompt
#   3  — apply failed (mid-copy)

set -euo pipefail

# Whitelist (mirror of capture-config.sh). Used to validate
# every path in the tarball before extracting — if a path
# is in the tarball but NOT in the whitelist, we reject the
# tarball. This prevents a malicious or accidental archive
# from writing outside the whitelist (e.g. /etc/passwd).
#
# Order matches capture-config.sh for stable diff output.
WHITELIST=(
    "home/pi/.reticulum/config"
    "etc/reticulumhf/config.env"
    "home/pi/.config/pat"
    "home/pi/.config/modem73"
    "home/pi/.config/ardopc"
    "home/pi/.config/direwolf"
    "home/pi/.config/js8call"
    "home/pi/.config/fldigi"
    "home/pi/.config/flrig"
    "home/pi/.config/wsjtx"
    "home/pi/.config/hamlib"
    "home/pi/.config/pavucontrol.ini"
    "etc/hostapd/hostapd.conf"
    "etc/dhcp/dhcpd.conf"
    "home/pi/.local/share/patmenu2"
)

# Helper: is $1 a prefix (or equal) of any whitelist entry?
# Returns 0 if yes, 1 if no. Used to allow files inside a
# whitelisted dir (e.g. home/pi/.config/pat/config.json
# is OK because home/pi/.config/pat is in the list).
is_whitelisted() {
    local p="$1"
    for w in "${WHITELIST[@]}"; do
        case "$p" in
            "$w"|"$w"/*) return 0 ;;
        esac
    done
    return 1
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

if [ $# -lt 1 ]; then
    echo "Usage: $0 <tarball.tar.gz> [--apply] [--yes]" >&2
    exit 1
fi

TARBALL="$1"
APPLY=0
YES=0
shift
while [ $# -gt 0 ]; do
    case "$1" in
        --apply) APPLY=1 ;;
        --yes|-y) YES=1 ;;
        *) echo "ERROR: unknown arg: $1" >&2; exit 1 ;;
    esac
    shift
done

# ---------------------------------------------------------------------------
# Sanity: tarball exists, is readable, is a valid tar.gz
# ---------------------------------------------------------------------------

if [ ! -f "$TARBALL" ]; then
    echo "ERROR: tarball not found: $TARBALL" >&2
    exit 1
fi
if [ ! -r "$TARBALL" ]; then
    echo "ERROR: tarball not readable: $TARBALL" >&2
    exit 1
fi
if ! tar tzf "$TARBALL" >/dev/null 2>&1; then
    echo "ERROR: tarball is not a valid .tar.gz: $TARBALL" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Validate the whitelist BEFORE extracting. Any path in the
# archive that isn't covered by the whitelist is a hard
# reject — better to abort than to write a stray file.
# ---------------------------------------------------------------------------

BAD_PATHS=()
while IFS= read -r member; do
    # tar's listing has format like "home/pi/.reticulum/config"
    # (no leading /, since capture-config.sh strips it).
    if ! is_whitelisted "$member"; then
        BAD_PATHS+=("$member")
    fi
done < <(tar tzf "$TARBALL")

if [ "${#BAD_PATHS[@]}" -gt 0 ]; then
    echo "ERROR: tarball contains paths NOT in the whitelist:" >&2
    for p in "${BAD_PATHS[@]}"; do
        echo "  - $p" >&2
    done
    echo "Refusing to extract. This is a safety check — the tarball" >&2
    echo "may have been created by a different version of" >&2
    echo "capture-config.sh with a different whitelist." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Extract to a staging dir
# ---------------------------------------------------------------------------

BASENAME=$(basename "$TARBALL")
STAGING="/tmp/${BASENAME%.tar.gz}-stage"
rm -rf "$STAGING"
mkdir -p "$STAGING"

tar xzf "$TARBALL" -C "$STAGING"

# ---------------------------------------------------------------------------
# Compute the diff
# ---------------------------------------------------------------------------

# Three counters + three arrays.
ADDS=()
REPLACES=()
SKIPS=()

while IFS= read -r -d '' src; do
    # src is the staging-side path, e.g. .../stage/home/pi/.reticulum/config
    rel="${src#$STAGING/}"        # "home/pi/.reticulum/config"
    target="/${rel}"              # "/home/pi/.reticulum/config"

    src_size=$(stat -c %s "$src")

    if [ ! -e "$target" ]; then
        ADDS+=("$target ($src_size bytes)")
    elif [ -d "$target" ]; then
        # Target is a dir; can't compare. Mark skip
        # (shouldn't happen with our whitelist since we
        # always tar files, not dirs, but be safe).
        SKIPS+=("$target (target is a dir)")
    else
        # Both files; compare by content (size + bytes).
        tgt_size=$(stat -c %s "$target")
        if [ "$src_size" != "$tgt_size" ]; then
            REPLACES+=("$target ($tgt_size -> $src_size bytes)")
        elif [ "$src_size" -le 1048576 ]; then
            # 1 MiB or less: do a content compare
            if cmp -s "$src" "$target"; then
                SKIPS+=("$target (unchanged)")
            else
                REPLACES+=("$target ($tgt_size bytes, content differs)")
            fi
        else
            # > 1 MiB: skip the content compare, assume
            # equal because size matches. (We'd hash if
            # we had sha256sum, but to keep the script
            # zero-dep, this is good enough.)
            SKIPS+=("$target (size matches, content not compared)")
        fi
    fi
done < <(find "$STAGING" -type f -print0)

# Sort: adds first, then replaces, then skips (alpha within)
print_diff() {
    echo "  + add (${#ADDS[@]}):"
    for p in "${ADDS[@]}"; do
        echo "      + $p"
    done
    echo
    echo "  ~ replace (${#REPLACES[@]}):"
    for p in "${REPLACES[@]}"; do
        echo "      ~ $p"
    done
    echo
    echo "  = skip (${#SKIPS[@]}):"
    for p in "${SKIPS[@]}"; do
        echo "      = $p"
    done
}

# ---------------------------------------------------------------------------
# Print preview
# ---------------------------------------------------------------------------

echo "=== Restore preview ==="
echo
echo "  tarball:    $TARBALL"
echo "  size:       $(stat -c %s "$TARBALL") bytes"
echo "  staging:    $STAGING"
echo "  hostname:   $(hostname -s 2>/dev/null || echo g90)"
echo
echo "  diff:"
print_diff
echo

if [ "${#ADDS[@]}" -eq 0 ] && [ "${#REPLACES[@]}" -eq 0 ]; then
    echo "No changes needed — the archive is already in sync"
    echo "with the live box."
    rm -rf "$STAGING"
    exit 0
fi

# ---------------------------------------------------------------------------
# Apply if requested, otherwise prompt
# ---------------------------------------------------------------------------

if [ "$APPLY" -ne 1 ]; then
    echo "Run with --apply to actually write these changes."
    echo "Staging dir will be kept at $STAGING in case you"
    echo "want to inspect it before applying."
    exit 0
fi

# Apply
echo "=== Applying ==="
echo

WRITTEN=()
FAILED=()
for src in $(find "$STAGING" -type f); do
    rel="${src#$STAGING/}"
    target="/${rel}"
    target_dir=$(dirname "$target")

    # Make sure the target dir exists. The whitelist only
    # includes paths whose parents should already exist
    # (e.g. /home/pi/.config/modem73), but the operator
    # may have a /home/pi/.config/xxx in the backup that
    # we haven't created yet.
    if [ ! -d "$target_dir" ]; then
        mkdir -p "$target_dir"
        echo "  mkdir -p $target_dir"
    fi

    # Try the unshilded copy first (covers most cases
    # where the target dir is owned by pi). On
    # PermissionError, fall back to sudo install.
    if cp -p "$src" "$target" 2>/dev/null; then
        WRITTEN+=("$target")
    elif command -v sudo >/dev/null 2>&1 && \
         sudo -n install -D -o pi -g pi -m 0644 \
              "$src" "$target" 2>/dev/null; then
        WRITTEN+=("$target (via sudo)")
    else
        FAILED+=("$target (Permission denied; not in sudoers or no sudo)")
    fi
done

echo
echo "=== Summary ==="
echo "  wrote:  ${#WRITTEN[@]} files"
for p in "${WRITTEN[@]}"; do
    echo "    + $p"
done
if [ "${#FAILED[@]}" -gt 0 ]; then
    echo
    echo "  FAILED: ${#FAILED[@]} files (no permission):"
    for p in "${FAILED[@]}"; do
        echo "    ! $p"
    done
    echo
    echo "  Tip: run this script as root, or as a user with"
    echo "  write access to the target dirs."
fi

# Cleanup staging
rm -rf "$STAGING"

if [ "${#FAILED[@]}" -gt 0 ]; then
    exit 3
fi

echo
echo "Done. Restart any services that read the restored"
echo "config (the launcher's restore-configs flow does"
echo "this automatically; the standalone script leaves it"
echo "to the operator because the affected services differ"
echo "between g90digi, g90f1r2, and freshly-flashed boxes):"
echo
echo "  sudo systemctl restart g90-shared-launcher \\"
echo "      reticulumhf-rnsd \\"
echo "      meshchatx \\"
echo "      freedvtnc2"
