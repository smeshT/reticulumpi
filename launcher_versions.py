#!/usr/bin/env python3
"""Version comparison + drift detection helpers for the launcher.

Extracted as a module so both /launcher-status and /launcher-update use
identical logic (they previously had duplicated inline copies).

Why this exists: the old check was `installed >= min_version` as a plain
string compare, which is wrong twice over:
  - "1.10.0" >= "1.9.0" is False lexically (string "1.10" < "1.9")
  - a floor can never detect DRIFT; 1.5.2 passes ">= 1.4.0" against a
    1.5.4 server, which is exactly the skew that breaks RNS shared-instance
    RPC (see memory: RNS multi-install shadowing, 2026-11-11)
"""

import re


def parse_version(v):
    """Return a comparable tuple of ints from a version string.

    Tolerates suffixes ("1.6.0rc1", "1.5.4.post2", "v1.0.7") by taking the
    leading numeric components. Non-numeric junk sorts as (0,).
    """
    if not v:
        return (0,)
    m = re.match(r"^v?(\d+(?:\.\d+)*)", str(v).strip())
    if not m:
        return (0,)
    return tuple(int(p) for p in m.group(1).split("."))


def cmp_version(a, b):
    """-1 / 0 / 1 for a < b / a == b / a > b, with tuple padding."""
    ta, tb = parse_version(a), parse_version(b)
    n = max(len(ta), len(tb))
    ta = ta + (0,) * (n - len(ta))
    tb = tb + (0,) * (n - len(tb))
    return (ta > tb) - (ta < tb)


def check_pip_spec(spec, actual_pkgs_by_venv):
    """Evaluate one manifest pip_packages entry.

    Supports three modes, in precedence order:
      exact_version   — installed must equal this exactly
      min_version     — installed must be >= this (legacy behaviour)
      consistency_group — handled separately by check_consistency()

    Returns (ok: bool, detail: str, package, venv).
    """
    venv = spec.get("venv", "")
    pkg = spec.get("package", "")
    installed = actual_pkgs_by_venv.get(venv, {}).get(pkg)

    if installed is None:
        # A venv that doesn't exist at all reads differently from a venv
        # that exists without the package — the operator needs to know
        # which, because one means "not installed" and the other means
        # "this box predates the package entirely".
        if venv not in actual_pkgs_by_venv:
            return (False, f"venv {venv} not present", pkg, venv)
        return (False, "not installed", pkg, venv)

    exact = spec.get("exact_version")
    if exact:
        ok = (str(installed).strip() == str(exact).strip())
        detail = f"{installed}" if ok else f"{installed} (need exactly {exact})"
        return (ok, detail, pkg, venv)

    min_v = spec.get("min_version")
    if min_v:
        ok = cmp_version(installed, min_v) >= 0
        detail = f"{installed}" if ok else f"{installed} (need >= {min_v})"
        return (ok, detail, pkg, venv)

    # No constraint declared; report but pass.
    return (True, f"{installed}", pkg, venv)


def check_consistency(groups, actual_pkgs_by_venv):
    """Detect cross-venv version drift for a package.

    This is the check that catches g90digi's failure mode: rnsd on
    1.5.4 while lxmf and meshchatx venvs carry 1.5.2. Every version
    satisfies ">= 1.4.0", so a floor check stays green while the
    shared-instance RPC protocol silently drifts.

    groups: manifest list of {package, venvs: [...], required_in: [...]}
            (required_in is optional; if given, those venvs must have it
             installed for the group to be considered complete)

    Returns list of (ok, detail, label) tuples.
    """
    rows = []
    for grp in groups or []:
        pkg = grp.get("package", "")
        venvs = grp.get("venvs", [])
        required_in = grp.get("required_in") or []

        found = {}
        for v in venvs:
            ver = actual_pkgs_by_venv.get(v, {}).get(pkg)
            if ver is not None:
                found[v] = str(ver).strip()

        missing_required = [v for v in required_in if v not in found]
        if missing_required:
            rows.append((
                False,
                f"missing in {', '.join(missing_required)}",
                f"{pkg} consistency",
            ))
            continue

        if len(found) < 2:
            rows.append((True, "only one copy, nothing to compare",
                         f"{pkg} consistency"))
            continue

        distinct = set(found.values())
        if len(distinct) == 1:
            rows.append((True, f"all on {distinct.pop()}",
                         f"{pkg} consistency"))
        else:
            parts = " vs ".join(f"{v}={ver}" for v, ver in sorted(found.items()))
            rows.append((False, f"DRIFT: {parts}", f"{pkg} consistency"))

    return rows


def converge_plan(pins, actual_pkgs_by_venv):
    """Work out the pip commands needed to reach the pinned versions.

    pins: manifest list of {venv, package, exact_version}

    Returns list of (venv, package, current, target) for anything out of
    line. Caller decides whether to act.
    """
    plan = []
    for spec in pins or []:
        exact = spec.get("exact_version")
        if not exact:
            continue
        venv = spec.get("venv", "")
        pkg = spec.get("package", "")
        if venv not in actual_pkgs_by_venv:
            continue  # venv absent; pipx can't be upgraded into a void
        current = actual_pkgs_by_venv.get(venv, {}).get(pkg)
        if current is None:
            plan.append((venv, pkg, None, str(exact)))
        elif str(current).strip() != str(exact).strip():
            plan.append((venv, pkg, str(current).strip(), str(exact)))
    return plan
