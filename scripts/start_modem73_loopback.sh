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
# with start_new_session=True, which already gives us our own session.
# Do NOT add `setsid` here — double-detaching makes setsid exit 255
# and the script aborts before modem73 actually launches.

pkill -f "modem73 --headless" 2>/dev/null
sleep 1

/usr/bin/modem73 \
  --headless \
  --config /home/pi/.config/modem73/settings \
  > /tmp/shared_launcher_modem73_loopback.log 2>&1 < /dev/null &

disown
exit 0
