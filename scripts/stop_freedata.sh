#!/bin/bash
# stop_freedata.sh — stop the freedata server.
#
# Sends SIGTERM to the server.py process. uvicorn handles SIGTERM
# cleanly (finishes in-flight requests, closes the DB connection).
# We do NOT send SIGKILL — a hard kill on a sqlite3 process can
# corrupt the database.
#
# If the server is wedged and SIGTERM doesn't take within ~5s, the
# launcher page's "Reboot Pi" button is the appropriate escalation.
# A SIGKILL is intentionally not offered in the launcher — sqlite
# corruption is worse than a brief hang.
#
# Hardened 2026-07-04: uses _lib_stop.sh like the other stop
# scripts (consistent with the 2026-06-23 launcher stop-script
# hardening). Note: stop_proc in _lib_stop.sh defaults to SIGKILL
# (per the lib's design — Qt apps ignore SIGTERM). We override
# with TERM here because the freedata server is a python/uvicorn
# process that DOES respect SIGTERM, and we want the clean
# shutdown.

LIB=/home/pi/sbitx/web/scripts/_lib_stop.sh
# shellcheck disable=SC1091
source "$LIB"

fail=0

# pgrep -f matches against the full command line. "freedata_server/server.py"
# appears in the cmdline of the parent process AND any child python
# processes it forks. Matching once is enough.
stop_proc "freedata_server/server.py" TERM || fail=1

# Belt-and-suspenders: if the port is still bound after 5s, the
# server is wedged. Don't SIGKILL (see header comment) — just
# report the situation so the user can decide.
sleep 5
if ss -tln 2>/dev/null | grep -q ':5001 '; then
    echo "freedata: warning — port 5001 still bound after SIGTERM"
    echo "freedata: a wedged uvicorn may need manual intervention;"
    echo "freedata: check /tmp/my_launcher_freedata.log for the cause."
    fail=1
fi

[ "$fail" -eq 0 ] && echo "freedata stopped" || echo "freedata stop had errors"
exit $fail
