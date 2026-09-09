#!/bin/bash
# Start the modem73 instance bound to the ALSA Loopback device for
# self-loopback testing of the Reticulum-over-OFDM channel. This is a
# *second* modem73 (the g90test box already runs one in terminal UI mode
# on whatever audio device the operator configured) — dedicated to the
# Reticulum-on-Loopback bearer configured in ~/.reticulum/config.
#
# Pass --config explicitly. modem73 in --headless mode WITHOUT --config
# only loads a subset of settings (audio, com, callsign); --port,
# bind_address, control_bind_address, etc. are silently ignored. Passing
# --config <full path> tells modem73 to load the whole settings file
# (the same one the TUI writes to). On sbitx this fixes the port 8001
# conflict with freedvtnc2.service (settings file says port=8002). On
# g90test it makes the KISS port match the Reticulum "[[Modem73]]"
# target_port. Without --config, both Reticulum integration is broken.
# (Found 2026-09-04 16:36 MDT while building the audio-reset button.)
#
# Detach model: shared_launcher/app.py invokes this via subprocess.Popen
# with start_new_session=True, which puts the script in its own session
# (via setsid). When the script exits, the kernel sends SIGHUP to all
# processes in the session — including backgrounded children. `disown`
# only removes the child from the shell's job table; it does NOT make
# the child immune to session-leader SIGHUP. The fix is `nohup` on
# the child itself, which tells the kernel "ignore SIGHUP" for that
# process. (We previously used `disown` here; the modem73 would run
# for ~2s, receive SIGHUP when this script exited, and die. Discovered
# 2026-09-09 15:54 MDT while debugging the "Modem73 Interface: Start"
# button silently failing.) The other start_*.sh scripts (fldigi, flrig,
# js8call, wsjtx) already use nohup and work correctly.
pkill -f "modem73 --headless" 2>/dev/null
sleep 1

nohup /usr/bin/modem73 \
  --headless \
  --config /home/pi/.config/modem73/settings \
  > /tmp/shared_launcher_modem73_loopback.log 2>&1 < /dev/null &

exit 0
