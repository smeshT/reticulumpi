#!/bin/bash
# start_freedata.sh — start the freedata server (FastAPI/uvicorn) in
# the background.
#
# FreeDATA serves its own web UI on http://<host>:5001/gui, so this
# does NOT need the Xvfb desktop — a browser pointed at the URL is
# all you need to compose/send ARQ messages.
#
# The codec2 native library is bundled with the freedata install but
# the install on this box shipped an x86-64 build of the .so. We
# replaced it with the aarch64 one from /usr/local/lib/ (the
# freedata-custom build), so the Python codec2 module can dlopen it.
# If you ever rebuild freedata from source, the right-arch .so is
# at FreeDATA/freedata_server/lib/codec2/build_linux/src/libcodec2.so.
#
# Idempotent: if a freedata server is already listening on :5001,
# this is a no-op.
#
# Created 2026-07-04 to add the "FreeDATA" row to my_launcher.

# Refuse to start if freedata is already serving :5001.
if ss -tln 2>/dev/null | grep -q ':5001 '; then
    exit 0
fi

# Refuse to start if another process is already running the server
# script (in case the port check above misses a race).
if pgrep -f 'freedata_server/server.py' >/dev/null 2>&1; then
    exit 0
fi

# FreeDATA's run script and server.py use relative paths, so we have
# to cd into the install dir. Keep this in sync with where the
# install-freedata-linux.sh script placed the install (currently
# /home/pi/freedata).
cd /home/pi/freedata || exit 1

# The bundled FreeDATA-hamlib install needs to be on PATH (for the
# rigctl binaries) and LD_LIBRARY_PATH (for libhamlib.so).
export PATH=./FreeDATA-hamlib/bin:$PATH
export LD_LIBRARY_PATH=./FreeDATA-hamlib/lib:${LD_LIBRARY_PATH:-}

# Activating the venv ensures `python3` resolves to the freedata
# venv's interpreter (which has the freedata_server package installed
# at lib/python3.11/site-packages/freedata_server/).
source ./FreeDATA-venv/bin/activate

# Config + database paths. The server reads these from env vars, NOT
# from defaults — without them, the server exits with a path error.
export FREEDATA_CONFIG=$HOME/.config/FreeDATA/config.ini
export FREEDATA_DATABASE=$HOME/.config/FreeDATA/freedata-messages.db

# Run in the background, redirect stdio, detach. The launcher's HTTP
# request returns immediately; uvicorn keeps running until killed.
nohup python3 FreeDATA/freedata_server/server.py \
    >/tmp/my_launcher_freedata.log 2>&1 &

exit 0
