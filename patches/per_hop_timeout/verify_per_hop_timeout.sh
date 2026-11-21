#!/usr/bin/env bash
# verify_per_hop_timeout.sh -- confirm the patch survived an upgrade.
#
# pipx upgrade reinstalls the wheel and silently discards the patch.
# There is no announcement; links just start failing again on HF.
# Run this after every `pipx upgrade reticulum` (or on a schedule).
#
# Exit 0 = patched, 1 = reverted or missing, 2 = RNS not found.

set -u

# pipx uses ~/.local/pipx/venvs on some installs and ~/.local/share/pipx/venvs
# on others, so try both before giving up.
if [ $# -ge 1 ]; then
    VENV="$1"
else
    VENV=""
    for base in "$HOME/.local/pipx/venvs" "$HOME/.local/share/pipx/venvs"; do
        if [ -d "$base/rns" ]; then VENV="$base/rns"; break; fi
    done
    [ -n "$VENV" ] || VENV="$HOME/.local/pipx/venvs/rns"
fi

RNS=$(ls -d "$VENV"/lib/python3.*/site-packages/RNS 2>/dev/null | tail -1)
if [ -z "${RNS:-}" ]; then
    echo "ERROR: RNS package not found under $VENV" >&2
    exit 2
fi

fail=0

check() {
    local file="$1" needle="$2" label="$3"
    if grep -q -- "$needle" "$file" 2>/dev/null; then
        printf '  OK       %s\n' "$label"
    else
        printf '  REVERTED %s\n' "$label"
        fail=1
    fi
}

echo "RNS: $RNS"
echo

check "$RNS/Interfaces/Interface.py" 'self.per_hop_timeout = None' \
      'Interface.py: per_hop_timeout default'
check "$RNS/Link.py" 'def per_hop_timeout_for' \
      'Link.py: helper'
check "$RNS/Link.py" 'per_hop_timeout_for(getattr(packet' \
      'Link.py: responder call site'
check "$RNS/Link.py" 'per_hop_timeout_for(_first_hop_interface)' \
      'Link.py: initiator call site'

echo
if [ "$fail" -eq 0 ]; then
    echo "RESULT: patched"
    exit 0
fi

echo "RESULT: REVERTED -- re-apply with:"
echo "  python3 apply_per_hop_timeout.py --apply --venv $VENV"
echo "  then: sudo systemctl restart rnsd"
exit 1
