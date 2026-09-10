"""Config backup / restore for the g90 shared launcher.

The pattern is the sbitx toolbox approach: capture the live box's
config files into a tarball, rotate to last 5 archives, and let
the operator download. Restore is a two-step flow: upload +
preview diff, then a second POST to actually apply.

This file is imported by app.py as `from scripts.config_backup
import *` (after the SCRIPTS path is set up). The launcher
routes are thin wrappers around the functions in this module.

Box-specific (per operator 2026-09-09 21:38 MDT): captures
include the box's Reticulum node identity. Restoring this
backup to a different box will give the new box the same
identity — useful for fleet rebuilds (so other boxes can find
it), but operators should be aware.

Whitelist (2026-09-09 21:38 MDT): js8call, fldigi, flrig, wsjtx
are all included. The whitelist is closed (no globs); to add a
new path, edit CONFIG_WHITELIST below and ship a release.
"""

import io
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import datetime

# Whitelist of paths to back up. Closed list; no globs; no
# `/home/pi/` (would sweep in bash history, ssh keys, etc.).
# Each entry: (absolute_path, is_dir). Directories are walked
# recursively; missing files are silently skipped (so a path
# that's only on some boxes is fine).
CONFIG_WHITELIST = [
    ("/home/pi/.reticulum/config",                                  False),
    ("/etc/reticulumhf/config.env",                                 False),
    ("/home/pi/.config/pat",                                        True),
    ("/home/pi/.config/modem73",                                    True),
    ("/home/pi/.config/ardopc",                                     True),
    ("/home/pi/.config/direwolf",                                   True),
    ("/home/pi/.js8call",                                   True),  # JS8Call
    ("/home/pi/.fldigi",                                    True),  # fldigi
    ("/home/pi/.flrig",                                     True),  # flrig
    ("/home/pi/.wsjtx",                                     True),  # WSJT-X
    ("/home/pi/.config/hamlib",                                     True),
    ("/home/pi/.config/pavucontrol.ini",                            False),
    ("/etc/hostapd/hostapd.conf",                                   False),
    ("/etc/dhcp/dhcpd.conf",                                        False),
    ("/home/pi/.local/share/patmenu2",                              True),
]

# Where backups are stored on the box. Each archive is
# g90digi-configs-<hostname>-v<version>-<timestamp>.tar.gz
# (or g90test-configs-, g90f1r2-configs-, etc., depending on
# the box). Rotation: keep at most MAX_BACKUPS=5, deleting the
# oldest by mtime when a new one is created.
BACKUP_DIR = os.environ.get(
    "LAUNCHER_BACKUP_DIR",
    "/home/pi/shared_launcher/backups",
)
MAX_BACKUPS = 5


def get_hostname():
    """Return the short hostname, falling back to 'g90' if unknown.
    The hostname is in the filename so a multi-box operator can
    tell which box each archive came from."""
    try:
        out = subprocess.run(
            ["hostname", "-s"],
            capture_output=True, text=True, timeout=2,
        )
        name = (out.stdout or "").strip()
        return name if name else "g90"
    except Exception:
        return "g90"


def get_launcher_version():
    """Read the launcher's own version (e.g. 'v0.6.45') from
    the latest git tag. If the launcher is image-baked (no
    .git/), return 'image-baked'."""
    try:
        out = subprocess.run(
            ["git", "-C", os.environ.get("LAUNCHER_DIR",
                                          "/home/pi/shared_launcher"),
             "describe", "--tags", "--abbrev=0"],
            capture_output=True, text=True, timeout=2,
        )
        return (out.stdout or "").strip() or "image-baked"
    except Exception:
        return "image-baked"


def build_backup_tarball():
    """Build a tar.gz in memory of all whitelist files that
    exist on the box. Returns (tar_bytes, manifest_dict)
    where manifest_dict is a summary that goes into the page
    that shows the download."""

    buf = io.BytesIO()
    included = []
    skipped = []

    # Use a fixed timestamp for determinism (so byte-equal
    # runs of the same backup produce the same tarball, modulo
    # mtimes in the captured files). 2026-09-09 12:00:00 UTC
    # = boot of the freshly-built reticulumpi box.
    epoch_fixed = int(
        datetime.datetime(2026, 9, 9, 12, 0, 0,
                          tzinfo=datetime.timezone.utc).timestamp()
    )

    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        # Deterministic mtime for the archive itself.
        # Per-file mtimes are not normalized (they reflect
        # the source files' real mtimes), but the tar
        # header for the archive as a whole is fixed so
        # byte-equal runs of the same backup produce the
        # same tarball, modulo captured-file contents.
        tar.mtime = epoch_fixed
        for path, is_dir in CONFIG_WHITELIST:
            if not os.path.exists(path):
                skipped.append(path)
                continue
            try:
                tar.add(path, arcname=path.lstrip("/"),
                        recursive=is_dir)
                included.append(path)
            except (PermissionError, OSError) as e:
                # Don't fail the whole backup because one
                # file was unreadable. Operator sees the
                # skip in the manifest and can chmod+retry.
                skipped.append(f"{path} (error: {e})")

    buf.seek(0)
    manifest = {
        "included": included,
        "skipped": skipped,
        "hostname": get_hostname(),
        "version": get_launcher_version(),
        "created_utc": datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds"),
        "total_files": len(included),
    }
    return buf.getvalue(), manifest


def backup_filename(manifest):
    """Construct the on-disk filename for a new backup. The
    hostname + version + timestamp combo is unique enough for
    a 5-archive rotation."""
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return (
        f"g90-configs-{manifest['hostname']}"
        f"-{manifest['version']}-{ts}.tar.gz"
    )


def save_backup_and_rotate(tar_bytes, manifest):
    """Write a new backup to BACKUP_DIR, then keep only the
    last MAX_BACKUPS files (sorted by mtime). Returns the
    absolute path of the new file."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    fname = backup_filename(manifest)
    fpath = os.path.join(BACKUP_DIR, fname)
    with open(fpath, "wb") as f:
        f.write(tar_bytes)
    rotate_backups()
    return fpath


def rotate_backups():
    """Keep only the last MAX_BACKUPS archives in BACKUP_DIR.
    Sorted by mtime, oldest first; delete anything past the
    cap. Idempotent: a no-op when there are fewer than the
    cap."""
    if not os.path.isdir(BACKUP_DIR):
        return
    archives = sorted(
        (os.path.join(BACKUP_DIR, f)
         for f in os.listdir(BACKUP_DIR)
         if f.endswith(".tar.gz")),
        key=os.path.getmtime,
    )
    while len(archives) > MAX_BACKUPS:
        try:
            os.remove(archives[0])
        except OSError:
            pass
        archives.pop(0)


def list_backups():
    """Return a list of dicts describing each archive currently
    in BACKUP_DIR, sorted newest-first. Used by the restore
    page to let the operator pick an old archive to restore."""
    if not os.path.isdir(BACKUP_DIR):
        return []
    out = []
    for f in sorted(os.listdir(BACKUP_DIR),
                    key=lambda x: os.path.getmtime(
                        os.path.join(BACKUP_DIR, x)),
                    reverse=True):
        if not f.endswith(".tar.gz"):
            continue
        fpath = os.path.join(BACKUP_DIR, f)
        try:
            sz = os.path.getsize(fpath)
            mt = datetime.datetime.fromtimestamp(
                os.path.getmtime(fpath)).isoformat(
                    timespec="seconds", sep=" ")
        except OSError:
            continue
        out.append({"filename": f, "size": sz, "mtime": mt})
    return out


# ---------------------------------------------------------------------------
# Restore flow
# ---------------------------------------------------------------------------

# Restore staging area. Live across requests because the
# operator goes upload -> preview -> apply, and we don't want
# to re-extract on the apply step. Keyed by an opaque token
# (generated by the upload handler, returned in the URL of
# the preview page). Tokens are 32 hex chars from
# /dev/urandom. The staging dir is wiped at apply time
# (success) and on a "discard" button (cleanup).
RESTORE_STAGING = os.environ.get(
    "LAUNCHER_RESTORE_STAGING",
    "/home/pi/shared_launcher/restore-staging",
)


def _new_token():
    """Return a 32-hex-char token. Use Python's `secrets`
    module so we don't depend on /usr/bin/xxd being on
    the box (ReticulumHF base doesn't ship it)."""
    import secrets
    return secrets.token_hex(16)


def extract_to_staging(tar_bytes):
    """Extract the upload to a fresh subdir of RESTORE_STAGING
    keyed by a new token. Returns (token, staging_dir,
    members_list) where members_list is a list of (path,
    size_bytes) for every file in the archive (after filtering
    out path-traversal attempts)."""
    os.makedirs(RESTORE_STAGING, exist_ok=True)
    token = _new_token()
    staging = os.path.join(RESTORE_STAGING, token)
    os.makedirs(staging, exist_ok=True)

    members = []
    try:
        # Open the upload as a file-like object.
        bio = io.BytesIO(tar_bytes)
        with tarfile.open(fileobj=bio, mode="r:gz") as tar:
            for m in tar.getmembers():
                # Strip the leading "/" from the arcname so
                # files extract as relative to staging/.
                # Also reject any path containing ".." — a
                # malformed archive could try to write
                # outside the staging dir.
                arc = m.name.lstrip("/")
                if ".." in arc.split("/"):
                    continue
                m.name = arc
                tar.extract(m, path=staging)
                members.append((arc, m.size))
    except tarfile.TarError as e:
        # Clean up the bad staging dir and re-raise.
        shutil.rmtree(staging, ignore_errors=True)
        raise ValueError(f"could not read tarball: {e}") from e

    return token, staging, members


def compute_diff(staging):
    """For every file in `staging`, decide what would happen
    if we applied it. Returns a list of dicts with:
       path    — full path on the live system
       action  — "add" (file doesn't exist on the box),
                 "replace" (file exists, contents differ),
                 "skip" (file exists, contents are identical)
       size    — bytes
    Plus a top-level `action_required` (any add or replace).
    """
    diffs = []
    action_required = False
    for dirpath, _dirs, files in os.walk(staging):
        for f in files:
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, staging)
            target = "/" + rel  # staging is rooted at /

            if not os.path.exists(target):
                diffs.append({"path": target, "action": "add",
                              "size": os.path.getsize(full)})
                action_required = True
            else:
                # Compare by mtime + size (cheap), or by hash
                # for small files (definitive). The cheap
                # check is "are these bytes the same?" via
                # a quick read+compare.
                local_size = os.path.getsize(target)
                up_size = os.path.getsize(full)
                if local_size != up_size:
                    diffs.append({
                        "path": target,
                        "action": "replace",
                        "size": up_size,
                    })
                    action_required = True
                else:
                    # Same size; do a content compare for
                    # small files. Skip hash for large ones
                    # to keep the preview fast.
                    same = True
                    if up_size <= 1024 * 1024:  # 1 MiB
                        with open(target, "rb") as a, \
                             open(full, "rb") as b:
                            same = (a.read() == b.read())
                    if not same:
                        diffs.append({
                            "path": target,
                            "action": "replace",
                            "size": up_size,
                        })
                        action_required = True
                    else:
                        diffs.append({
                            "path": target,
                            "action": "skip",
                            "size": up_size,
                        })
    diffs.sort(key=lambda d: (d["action"] != "add",
                              d["action"] != "replace",
                              d["path"]))
    return {"items": diffs, "action_required": action_required}


def apply_staging(staging):
    """Walk the staging dir and copy every file to its
    target path on the live system, replacing any existing
    file. The staging root maps to /, so
    `staging/home/pi/.reticulum/config` becomes
    `/home/pi/.reticulum/config`.

    Some target dirs are owned by root (e.g. /home/pi/.config/pat/
    when the pat .deb created config.json with root:root). The
    launcher runs as pi, so the unshilded shutil.copy2 would
    fail with PermissionError. v0.6.48 fix: if shutil.copy2
    raises PermissionError, retry via `sudo install -o pi -g pi
    -m 0644`. Falls back to root:root if sudo isn't available,
    but the launcher's user is in sudoers (nopiasswd) on
    every deployed g90. The retry is bounded so a non-perm
    OSError (e.g. ENOSPC) still bubbles up.

    Returns a list of paths that were written (suitable for
    the post-apply page that says "we wrote these files")."""
    written = []
    for dirpath, _dirs, files in os.walk(staging):
        for f in files:
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, staging)
            target = "/" + rel

            # Make sure the parent dir exists. The whitelist
            # only includes paths whose parents already
            # exist (e.g. /home/pi/.config/modem73), but
            # the operator might have a /home/pi/.config/xxx
            # in the backup that we haven't created yet.
            os.makedirs(os.path.dirname(target), exist_ok=True)

            # Try the unshilded copy first (covers most
            # cases where the target dir is owned by pi).
            # On PermissionError, fall back to sudo install.
            try:
                shutil.copy2(full, target)
            except PermissionError:
                # `install -D` creates parent dirs; -o/-g/-m
                # set ownership/perm. The staging file is
                # passed as the source.
                subprocess.run(
                    ["sudo", "-n", "install", "-D",
                     "-o", "pi", "-g", "pi", "-m", "0644",
                     full, target],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
            written.append(target)
    return written


def discard_staging(token):
    """Remove a staging dir (called when the operator cancels
    the restore preview)."""
    staging = os.path.join(RESTORE_STAGING, token)
    shutil.rmtree(staging, ignore_errors=True)


# Services that should be restarted after a config restore,
# because their in-memory state was loaded from one of the
# files we just replaced. Ordered: leaves first, then
# parents, then the long-lived daemons.
RESTORE_RESTART_SERVICES = [
    "freedvtnc2.service",
    "reticulumhf-rnsd.service",
    "meshchatx.service",
    "g90-shared-launcher.service",  # picks up new app.py if any
]


def restart_services_after_restore():
    """Detached restart of all services that read the
    restored config files. The launcher's own service is
    in the list — it'll go down briefly but the operator
    can re-click the launcher URL after a few seconds.
    Detached so the HTTP response returns immediately
    (the operator's POST will see HTTP 302 before the
    service actually restarts)."""
    for svc in RESTORE_RESTART_SERVICES:
        try:
            subprocess.Popen(
                ["sudo", "-n", "systemctl", "restart", svc],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            pass
