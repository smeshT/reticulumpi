#!/bin/bash
# Stop the modem73 Loopback instance started by start_modem73_loopback.sh.
# Only the Loopback instance (--headless) — leaves the g90test box primary
# modem73 (UI mode) and freedvtnc2 untouched.
#
# The pkill pattern matches the loopback script's invocation: pkill -f
# "modem73 --headless" rather than the specific --port 8101 string we
# used to use. Reason: per operator 2026-09-04, the launcher should not
# pin the port (it comes from ~/.config/modem73/settings). The pkill
# target follows the same principle — match the *mode* (headless)
# rather than the *port* (which is configurable).

# || true so a no-match exit does not trip the Flask route into HTTP 500.
pkill -f "modem73 --headless" 2>/dev/null || true
sleep 1
exit 0
