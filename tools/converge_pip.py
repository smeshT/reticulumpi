#!/usr/bin/env python3
"""Converge pipx venv package versions to the launcher manifest's pins.

Run as a SEPARATE PROCESS by the update flow, against the freshly
checked-out tree. That separation is the whole point: the update handler
is executing the previous version's code, so convergence logic written
inline there is always stale, and a fix to it can never apply on the
click that installs it. Running this file from the new checkout means
the new logic always takes effect.

Usage:
    python3 tools/converge_pip.py --manifest releases/launcher/v1.1.3.json
    python3 tools/converge_pip.py --manifest ... --dry-run

Exit codes:
    0  everything is at its pinned version (or was successfully converged)
    1  one or more installs failed
    2  could not read current state / manifest

Every line printed is copied verbatim into the launcher's update log, so
keep output human-readable.
"""

import argparse
import json
import os
import subprocess
import sys

# launcher_versions.py lives in the launcher root, one level up from tools/.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import launcher_versions  # noqa: E402

PIPX_VENVS = os.path.join(os.path.expanduser("~"), ".local", "pipx", "venvs")


def collect_state(venvs):
    """Return {venv: {package: version}} by asking each venv's own python.

    Mirrors what scripts/collect-box-status.sh does, but scoped to the
    venvs the manifest actually pins so the update does not pay for a
    full box-status collection.
    """
    state = {}
    for venv in venvs:
        py = os.path.join(PIPX_VENVS, venv, "bin", "python")
        if not os.path.isfile(py):
            continue
        try:
            out = subprocess.run(
                [py, "-m", "pip", "list", "--format=freeze"],
                capture_output=True, text=True, timeout=30,
            ).stdout
        except Exception as e:
            print(f"  WARNING: could not list {venv}: {e}")
            continue
        pkgs = {}
        for line in out.splitlines():
            if "==" in line:
                name, ver = line.split("==", 1)
                pkgs[name.strip()] = ver.strip()
        state[venv] = pkgs
    return state


def order_plan(plan):
    """Server venv first; within a venv, `rns` last.

    lxmf and meshchatx pull rns as a dependency, so installing rns first
    lets the resolver move it again and undo the pin.
    """
    return sorted(plan, key=lambda t: (
        0 if t[0] == "rns" else 1,
        t[0],
        0 if t[1] != "rns" else 1,
        t[1],
    ))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan without installing anything")
    args = ap.parse_args()

    try:
        with open(args.manifest) as f:
            manifest = json.load(f)
    except Exception as e:
        print(f"pip converge: cannot read manifest {args.manifest}: {e}")
        return 2

    pins = manifest.get("components", {}).get("pip_packages", [])
    if not pins:
        print("pip converge: manifest has no pip_packages; nothing to do")
        return 0

    venvs = sorted({p.get("venv", "") for p in pins if p.get("venv")})
    state = collect_state(venvs)
    if not state:
        print("pip converge: could not read any venv state; NOT converging")
        return 2

    plan = launcher_versions.converge_plan(pins, state)
    if not plan:
        have = ", ".join(
            f"{v}={state.get(v, {}).get('rns', '?')}" for v in venvs
        )
        print(f"pip converge: already at pinned versions ({have})")
        return 0

    plan = order_plan(plan)
    print(f"pip converge: {len(plan)} package(s) to change")
    for venv, pkg, cur, tgt in plan:
        print(f"  {venv}/{pkg}: {cur or 'absent'} -> {tgt}")

    if args.dry_run:
        print("pip converge: dry run, nothing installed")
        return 0

    failed = 0
    for venv, pkg, cur, tgt in plan:
        py = os.path.join(PIPX_VENVS, venv, "bin", "python")
        if not os.path.isfile(py):
            print(f"  SKIP {venv}/{pkg}: venv missing")
            continue
        try:
            r = subprocess.run(
                [py, "-m", "pip", "install",
                 "--disable-pip-version-check", "-q", f"{pkg}=={tgt}"],
                capture_output=True, text=True, timeout=300,
            )
        except subprocess.TimeoutExpired:
            print(f"  FAILED {venv}/{pkg}: timeout")
            failed += 1
            continue
        except Exception as e:
            print(f"  FAILED {venv}/{pkg}: {e}")
            failed += 1
            continue

        if r.returncode == 0:
            print(f"  {venv}/{pkg}=={tgt} installed")
        else:
            msg = (r.stderr or r.stdout or "").strip().splitlines()
            tail = msg[-1] if msg else "no output"
            print(f"  FAILED {venv}/{pkg}: {tail[:200]}")
            failed += 1

    # Re-read and report the end state honestly. A "success" exit code
    # with unchanged versions is exactly the failure mode this tool exists
    # to prevent.
    after = collect_state(venvs)
    remaining = launcher_versions.converge_plan(pins, after)
    if remaining:
        print(f"pip converge: {len(remaining)} package(s) still off-pin")
        for venv, pkg, cur, tgt in remaining:
            print(f"  {venv}/{pkg}: {cur or 'absent'} (want {tgt})")
        return 1
    print("pip converge: all venvs at pinned versions")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
