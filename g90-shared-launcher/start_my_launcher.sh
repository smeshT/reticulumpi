#!/bin/bash
# start_my_launcher.sh — development helper. Use systemd in production.
#
# Run this to start the g90 shared launcher in the foreground, for
# quick iteration while editing app.py / templates / scripts. The
# systemd unit (g90-shared-launcher.service) is the canonical way to
# start the launcher on the g90 box.

set -e
cd "$(dirname "$0")"
exec /usr/bin/python3 app.py
