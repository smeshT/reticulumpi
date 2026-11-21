#!/usr/bin/env python3
"""
install.py -- put the per_hop_timeout patch back after an RNS upgrade.

Reticulum gives a link a limited time to establish: 6 seconds per hop by
default. That is sized for packet radio and LoRa. On HF at a few hundred bits
per second, a request and reply can take two minutes, so the default gives up
before the other station ever answers. Links then fail with a clean log and no
error at all.

This installer adds an optional `per_hop_timeout` config key so one interface
can wait longer while every other interface keeps the fast default.

It is additive and idempotent: running it twice is harmless, and running it
with no changes needed does nothing.

Usage:
    python3 install.py                 # patch the default environment
    python3 install.py --venv PATH     # patch a specific environment
    python3 install.py --dry-run       # show what would change
    python3 install.py --revert        # restore the newest backups
    python3 install.py --quiet         # only report problems (for ExecStartPre)

Exit codes:
    0  patched, already patched, or nothing to do
    1  failed, or the result did not verify
    2  RNS package not found

Read INSTRUCTIONS.md beside this file for the by-hand equivalent.
"""

import argparse
import glob
import os
import py_compile
import re
import shutil
import sys
import time

# --------------------------------------------------------------------------
# The edits. Each is (file, old, new, label). `old` must appear exactly once,
# which is what makes a silent half-patch impossible: if upstream changes the
# surrounding code, the count assertion fails and nothing is written.
# --------------------------------------------------------------------------

# The constant line has three possible forms in the wild, and the installer must
# not assume which one it finds:
#   stock     ESTABLISHMENT_TIMEOUT_PER_HOP = RNS.Reticulum.DEFAULT_PER_HOP_TIMEOUT
#   old patch ESTABLISHMENT_TIMEOUT_PER_HOP = 120      (or 240, hardcoded)
# The docstring below the assignment is the stable anchor across all of them.
CONSTANT_PATTERN = re.compile(
    r"^(\s*)ESTABLISHMENT_TIMEOUT_PER_HOP\s*=\s*(.+)$", re.M)
CONSTANT_STOCK_MARK = "DEFAULT_PER_HOP_TIMEOUT"

HELPER = '''
    @staticmethod
    def per_hop_timeout_for(interface):
        """Effective per-hop establishment timeout for an interface.

        Returns the interface's own `per_hop_timeout` when it sets one,
        otherwise the global ESTABLISHMENT_TIMEOUT_PER_HOP. A missing
        attribute and an explicit None both fall back; 0 is honoured as a
        real value so a caller can disable the timeout deliberately.
        """
        value = getattr(interface, "per_hop_timeout", None)
        if value is None:
            return Link.ESTABLISHMENT_TIMEOUT_PER_HOP
        return value
'''

RESPONDER_OLD = """link.establishment_timeout = Link.ESTABLISHMENT_TIMEOUT_PER_HOP * max(1, packet.hops) + Link.KEEPALIVE"""
RESPONDER_NEW = """link.establishment_timeout = (Link.per_hop_timeout_for(getattr(packet, "receiving_interface", None)) * max(1, packet.hops)
                                              + Link.KEEPALIVE)"""

# Upstream line-wraps the responder expression, so a verbatim match can fail on
# a cosmetic difference. These detect the patched form regardless of wrapping.
RESPONDER_PATCHED_MARKS = (
    'Link.per_hop_timeout_for(getattr(packet, "receiving_interface", None))',
)
INITIATOR_PATCHED_MARKS = (
    "Link.per_hop_timeout_for(_first_hop_interface)",
)

INITIATOR_OLD = """self.establishment_timeout += Link.ESTABLISHMENT_TIMEOUT_PER_HOP * max(1, RNS.Transport.hops_to(self.destination.hash))"""
INITIATOR_NEW = """self.establishment_timeout += Link.per_hop_timeout_for(_first_hop_interface) * max(1, RNS.Transport.hops_to(self.destination.hash))"""

INTERFACE_ANCHOR = "class Interface:"

MARK = "per_hop_timeout_for"


def find_rns(venv=None):
    """Locate the RNS package directory inside an environment.

    Order matters. Auto-detection prefers an environment called `rns`, because
    that is the one `rnsd` runs from and the one whose RNS matters most. Other
    environments (`lxmf`, `nomadnet`, `reticulum-meshchatx`) each carry their
    own RNS copy and must be patched separately with --venv.
    """
    candidates = []
    if venv:
        candidates.append(venv)
    else:
        home = os.path.expanduser("~")
        for base in (
            os.path.join(home, ".local", "pipx", "venvs"),
            os.path.join(home, ".local", "share", "pipx", "venvs"),
            os.path.join(home, ".venvs"),
        ):
            # `rns` first, then everything else, so an alphabetically earlier
            # environment like `lxmf` cannot win by accident.
            preferred = os.path.join(base, "rns")
            if os.path.isdir(preferred):
                candidates.append(preferred)
            for other in sorted(glob.glob(os.path.join(base, "*"))):
                if os.path.realpath(other) != os.path.realpath(preferred):
                    candidates.append(other)
        candidates.append(sys.prefix)

    for cand in candidates:
        for pkg in sorted(glob.glob(os.path.join(cand, "lib", "python3.*", "site-packages", "RNS"))):
            if os.path.isdir(pkg):
                return pkg
        for pkg in sorted(glob.glob(os.path.join(cand, "RNS"))):
            if os.path.isdir(pkg):
                return pkg
    return None


def read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def backup(path, stamp, seen):
    """Back up a file once per run, so the backup is the pre-run original.

    Taking a fresh backup per edit would leave a ladder of half-patched
    copies, and --revert would restore one of those instead of the original.
    """
    if path in seen:
        return seen[path]
    dest = "%s.bak-%s" % (path, stamp)
    shutil.copy2(path, dest)
    seen[path] = dest
    return dest


def patch(pkg, dry_run, quiet):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    seen = {}
    lines = []

    def report(msg):
        lines.append(msg)
        if not quiet:
            print(msg)

    link_py = os.path.join(pkg, "Link.py")
    iface_py = os.path.join(pkg, "Interfaces", "Interface.py")
    for path in (link_py, iface_py):
        if not os.path.isfile(path):
            report("ERROR: missing %s" % path)
            return 1

    report("RNS package: %s" % pkg)
    report("")

    results = []

    # 1. the helper, inserted immediately below the constant's docstring
    link_src = read(link_py)
    if MARK in link_src:
        report("  OK       %-46s Link.py" % "helper present")
        results.append("present")
    else:
        m = CONSTANT_PATTERN.search(link_src)
        if not m:
            report("  FAIL     %-46s constant not found" % "Link.py")
            return 1
        value = m.group(2).strip()
        if CONSTANT_STOCK_MARK in value:
            report("  note     constant is stock (%s)" % value)
        else:
            report("  note     constant is hardcoded %s -- an older patch is present" % value)
            report("           this installer leaves it alone; set per_hop_timeout per interface instead")

        # insert after the docstring that follows the assignment, so we never
        # have to match the assignment's right-hand side
        after = link_src.find('"""', m.end())
        if after == -1:
            report("  FAIL     %-46s docstring anchor not found" % "Link.py")
            return 1
        close = link_src.find('"""', after + 3)
        if close == -1:
            report("  FAIL     %-46s docstring not closed" % "Link.py")
            return 1
        insert_at = close + 3
        report("  apply    %-46s Link.py" % "helper below ESTABLISHMENT_TIMEOUT_PER_HOP")
        results.append("applied")
        if not dry_run:
            backup(link_py, stamp, seen)
            link_src = link_src[:insert_at] + "\n" + HELPER.rstrip() + "\n" + link_src[insert_at:]
            with open(link_py, "w", encoding="utf-8") as fh:
                fh.write(link_src)

    # 2. the two call sites
    for old, new, label, marks in (
        (RESPONDER_OLD, RESPONDER_NEW, "Link.py: responder call site", RESPONDER_PATCHED_MARKS),
        (INITIATOR_OLD, INITIATOR_NEW, "Link.py: initiator call site", INITIATOR_PATCHED_MARKS),
    ):
        src = read(link_py)
        if any(m in src for m in marks):
            report("  OK       %-46s already patched" % label)
            results.append("present")
            continue
        if src.count(old) != 1:
            report("  FAIL     %-46s matched %d times" % (label, src.count(old)))
            report("           The surrounding code differs from what this installer expects.")
            report("           Apply by hand using INSTRUCTIONS.md, then re-run --dry-run.")
            return 1
        report("  apply    %-46s Link.py" % label)
        if not dry_run:
            backup(link_py, stamp, seen)
            with open(link_py, "w", encoding="utf-8") as fh:
                fh.write(src.replace(old, new, 1))
        results.append("applied")

    # 3. the Interface default
    iface_src = read(iface_py)
    if "self.per_hop_timeout" in iface_src:
        report("  OK       %-46s Interface.py" % "per_hop_timeout default")
        results.append("present")
    else:
        m = re.search(r"^(\s+)self\.rxb\s*=\s*0", iface_src, re.M)
        if not m:
            report("  FAIL     %-46s anchor not found" % "Interface.py")
            report("           Look for def __init__ in Interface.py and add "
                   "self.per_hop_timeout = None by hand.")
            return 1
        indent = m.group(1)
        insert_at = m.end()
        line_end = iface_src.find("\n", insert_at)
        addition = "\n%sself.per_hop_timeout = None" % indent
        report("  apply    %-46s Interface.py" % "per_hop_timeout default")
        results.append("applied")
        if not dry_run:
            backup(iface_py, stamp, seen)
            iface_src = iface_src[:line_end] + addition + iface_src[line_end:]
            with open(iface_py, "w", encoding="utf-8") as fh:
                fh.write(iface_src)

    if dry_run:
        report("")
        report("dry run: nothing written")
        return 0

    if "applied" not in results:
        report("")
        report("Already patched. Nothing to do.")
        return 0

    # 4. compile check, restore on failure
    for path in (link_py, iface_py):
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as exc:
            report("")
            report("COMPILE FAILED: %s" % exc)
            report("Restoring backups...")
            restore(pkg, verbose=False)
            return 1

    # 5. drop stale bytecode so the next start picks up the source
    for cache in glob.glob(os.path.join(pkg, "**", "__pycache__"), recursive=True):
        for pyc in glob.glob(os.path.join(cache, "Link.*.pyc")):
            try:
                os.remove(pyc)
            except OSError:
                pass

    report("")
    report("Patched and compiled. Restart rnsd to load it:")
    report("    sudo systemctl restart rnsd")
    report("")
    report("Then check your config has, on the slow interface only:")
    report("    per_hop_timeout = 240")
    return 0


def restore(pkg, verbose=True):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    restored = 0
    for path in (
        os.path.join(pkg, "Link.py"),
        os.path.join(pkg, "Interfaces", "Interface.py"),
    ):
        backups = sorted(glob.glob(path + ".bak-*"))
        if not backups:
            if verbose:
                print("  no backup for %s" % os.path.basename(path))
            continue
        latest = backups[-1]
        if verbose:
            print("  restore  %-30s from %s" % (os.path.basename(path), os.path.basename(latest)))
        shutil.copy2(latest, path)
        restored += 1
    if restored:
        if verbose:
            print("")
            print("Restored. Restart rnsd to load the originals.")
        return 0
    if verbose:
        print("Nothing to restore.")
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--venv", help="environment containing RNS (e.g. ~/.local/pipx/venvs/rns)")
    ap.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    ap.add_argument("--revert", action="store_true", help="restore the newest backups")
    ap.add_argument("--quiet", action="store_true", help="only report problems")
    args = ap.parse_args()

    pkg = find_rns(args.venv)
    if pkg is None:
        sys.stderr.write("ERROR: could not find the RNS package.\n")
        sys.stderr.write("Pass the environment explicitly, for example:\n")
        sys.stderr.write("    python3 install.py --venv ~/.local/pipx/venvs/rns\n")
        return 2

    if args.revert:
        return restore(pkg)
    return patch(pkg, args.dry_run, args.quiet)


if __name__ == "__main__":
    sys.exit(main())
