# g90digi image state (snapshotted 2026-07-07)

This folder is a **portable snapshot** of the g90 box's
"image state" — the configuration files that were edited
or installed on top of the stock g90digi image. It exists
so that, when the remote g90 Pi comes back online, the
same edits can be reapplied to a fresh flash without
having to re-derive them.

The **shared launcher** (Flask app, port 8090) lives in
`/home/pi/shared_launcher/` on the g90 box and is
mirrored in the **parent** of this folder
(`g90-shared-launcher/`). See `memory/g90-project.md` for
the full architecture and deploy procedure.

## What's in this folder

### `QUICK-START.md`
A printable one-page guide for the new owner of the
g90 box. Contains: first-time setup steps (connect to
the AP, open the panel), what each button does,
troubleshooting, important notes. Print this and ship
it in the box with the Pi. Re-derive it for the
offline g90 (change the SSID, hostname, and IP) when
that one is updated for a new owner.

### `node-portal-templates/`
Edits to node-portal's Jinja templates. These are NOT in
the launcher's directory — they're in node-portal, which
runs on port 80.

- `index.html` — the wifi setup page (current state)
- `apps.html` — the original "apps" page (the launcher
  now has a button to it on the wifi page; on the apps
  page there's a button back to the shared launcher)
- `wifi.html` — the standalone wifi template (not
  currently used by node-portal app.py, kept for ref)
- `index.html.bak-20260707-2127` — pre-edits backup
- `index.html.bak-20260707-2129` — backup after script
  removal, before span removal
- `index.html.bak-20260707-2130` — backup after both
  apps buttons added

**To reapply on a fresh image:** copy
`node-portal-templates/index.html` and `apps.html` over
the corresponding files at
`/home/pi/node-portal/templates/` on the g90 box, then
`sudo systemctl restart node-portal.service`.

### `config/`
Configuration files that are stored on the g90 box but
not in the standard g90digi image defaults.

- `pat-config.json` — pat Winlink client config
  (N0CALL stub; user will edit MYCALLSIGN later)
  Permissions: 600. Location on g90:
  `/home/pi/.config/pat/config.json`
- `askpass-g90.sh` — password echo for non-tty sudo.
  Permissions: 755. Location on g90:
  `/home/pi/.local/bin/askpass-g90.sh`
  Contents: `#!/bin/bash\necho "6292"`
  (the g90 box's user password; only the user knows if
  this should be kept in plaintext — for the g90 this
  was OK because it's a local-only Pi, no public ssh)
- `reticulumhf-config.env` — the g90 image's ReticulumHF
  service config. Source of truth for the audio device
  index, rigctld port, freedvtnc2 command, etc.
  Location on g90: `/etc/reticulumhf/config.env`
- `start-novnc-session` — script that brings up the
  Xvfb + openbox + x11vnc + websockify stack. We
  changed the Xvfb geometry from 1280x720 to 1280x800
  to give the patmenu2 yad a bit more vertical room.
  Location on g90: `/usr/local/bin/start-novnc-session`
- `start-novnc-session.bak-20260707-2100` — pre-edit
  backup (the 1280x720 version)

**To reapply on a fresh image:** copy each file to its
location with the right permissions. The pat config and
askpass are user-specific (`pi`); the others are root.

### `systemd-units/`
Custom systemd units we created.

- `g90-shared-launcher.service` — the shared launcher
  (port 8090). User `pi`, group `pi`. **NOT enabled at
  boot** by default — it's started by hand or by a
  script.
  Location on g90:
  `/etc/systemd/system/g90-shared-launcher.service`
- `pat-http.service` — the pat Winlink web UI
  (port 5000). **Disabled at boot** by default
  (user wants pat-http off until they explicitly turn
  it on, to prevent accidental outbound from queued
  messages).
  Location on g90:
  `/etc/systemd/system/pat-http.service`

**To reapply on a fresh image:** copy to
`/etc/systemd/system/`, then
`sudo systemctl daemon-reload`. Do NOT `enable` either
by default — they're meant to be started on demand.

### `patmenu2-edits/`
Edits to the patmenu2 source.

- `start-pat-ardop` — modified to call
  `curl -X POST http://127.0.0.1:8090/start-pat-http`
  instead of `sudo systemctl restart pat@$USER`. Also
  removed the `xdg-open` line (the g90 has no browser).
- `start-pat-ardop.bak-20260707-0543` — pre-edit
  backup (the stock km4ack version)

**NOTE:** the yad's "Start/Stop Modem" button calls
`start-pat-ardop`, which still has the curl line. As of
2026-07-07, the yad's modem button doesn't actually
work (lxterminal isn't installed on the g90 image), so
the curl is dead code. When the yad is fixed, the curl
becomes a backdoor to start pat-http. The user
explicitly chose to leave this in (logged in
`memory/g90-project.md`).

**To reapply on a fresh image:** copy
`start-pat-ardop` over
`/home/pi/patmenu2/start-pat-ardop` on the g90 box.

## How to deploy the whole bundle to a fresh g90

```bash
# On the g90 box, after a fresh flash + firstboot:
sudo -A systemctl stop node-portal.service  # (so we can edit templates)

# Copy files into place:
scp -r /home/pi/.openclaw/workspace/g90-shared-launcher/* pi@g90:/tmp/g90-bundle/
# Or use the g90-imager-style script (to be written).

# Then on the g90:
# - shared launcher files -> /home/pi/shared_launcher/
# - node-portal templates -> /home/pi/node-portal/templates/
# - config/* -> their respective locations
# - systemd units -> /etc/systemd/system/, then daemon-reload
# - patmenu2-edits/start-pat-ardop -> /home/pi/patmenu2/

sudo -A systemctl daemon-reload
sudo -A systemctl start g90-shared-launcher.service
sudo -A systemctl start node-portal.service
```

The shared launcher's deploy pattern (separate from this
bundle) is documented in
`memory/g90-project.md`.
