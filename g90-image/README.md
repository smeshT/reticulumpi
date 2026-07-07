# g90 image state (snapshotted 2026-07-07, updated 2026-07-08)

This folder is a **portable snapshot** of the g90 box's
"image state" — the configuration files that were edited
or installed on top of the stock g90digi image. It exists
so that, when the remote g90 Pi comes back online, the
same edits can be reapplied to a fresh flash without
having to re-derive them.

The **shared launcher** (Flask app, port 8090) lives in
the **parent** of this folder. It is a git clone of
`/home/pi/repos/g90-launcher.git` on the nomadpi, NOT a
direct copy. The full architecture is documented in
`memory/g90-project.md`.

## Deploy pattern (git-based, as of 2026-07-08)

The workspace at `/home/pi/.openclaw/workspace/g90-shared-launcher/`
is a git working tree. The bare repo at
`/home/pi/repos/g90-launcher.git` is the central pull
target. Each g90 is a clone of that bare repo.

```bash
# 1. Commit your changes in the workspace
cd /home/pi/.openclaw/workspace/g90-shared-launcher
git add -A
git commit -m "Description of the change"
git push origin master

# 2. The g90 boxes pull the new code via the Update button
#    on the launcher's bottom row. That button calls
#    POST /update-from-server which runs:
#    cd /home/pi/shared_launcher && git pull --ff-only
#    sudo systemctl restart g90-shared-launcher.service
```

## First-time setup on a fresh g90 image

```bash
# On the g90 (after a fresh flash + firstboot):

# 1. Generate an SSH key (for git pull from the nomadpi)
ssh-keygen -t ed25519 -N "" -f /home/pi/.ssh/id_ed25519
cat /home/pi/.ssh/id_ed25519.pub  # copy to nomadpi's authorized_keys

# 2. Clone the launcher
sudo -A -u pi git clone pi@nomadpi.local:/home/pi/repos/g90-launcher.git /home/pi/shared_launcher
sudo chown -R pi:pi /home/pi/shared_launcher

# 3. Install the systemd unit
sudo cp /home/pi/shared_launcher/g90-shared-launcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now g90-shared-launcher.service

# 4. (If migrating from an old direct-copy install) move the
#    old /home/pi/shared_launcher out of the way first
sudo mv /home/pi/shared_launcher /home/pi/shared_launcher.old

# 5. Then proceed with steps 2-3

# 6. Copy the g90-image/ contents into place (only the
#    files the g90 image's firstboot didn't set up itself):
#    - config/reticulumhf-config.env -> /etc/reticulumhf/config.env
#    - config/hostapd.conf -> /etc/hostapd/hostapd.conf
#    - config/pat-config.json -> /home/pi/.config/pat/config.json
#    - config/askpass-g90.sh -> /home/pi/.local/bin/askpass-g90.sh
#    - config/start-novnc-session -> /usr/local/bin/start-novnc-session
#    - systemd-units/pat-http.service -> /etc/systemd/system/
#    - patmenu2-edits/start-pat-ardop -> /home/pi/patmenu2/start-pat-ardop
```

## What's in this folder

### `QUICK-START.md`
A printable one-page guide for the new owner of the
g90 box.

### `node-portal-templates/`
The wifi setup page (current + 3 backups), apps.html,
wifi.html. These live in node-portal, not the launcher.
The plan is to migrate them into the launcher (so
node-portal goes away); tracked in
`memory/g90-project.md` and the daily log.

### `config/`
- `pat-config.json` — pat Winlink config (N0CALL stub)
- `askpass-g90.sh` — g90 user password (6292), in plaintext
  (this is a local-only Pi, the trade-off is OK)
- `reticulumhf-config.env` — ReticulumHF service config
- `hostapd.conf` — wifi AP config (SSID, channel, etc.)
- `start-novnc-session` — script that brings up Xvfb + openbox + x11vnc

### `systemd-units/`
- `g90-shared-launcher.service` — the shared launcher (port 8090)
- `pat-http.service` — pat Winlink web UI (port 5000)

### `patmenu2-edits/`
`start-pat-ardop` modified to call
`curl -X POST http://127.0.0.1:8090/start-pat-http` instead
of `sudo systemctl restart pat@$USER`.

## When the offline g90 comes online

The wrappers `/tmp/ssh-g90digi-now.sh` and
`/tmp/ssh-g90digi-tar.sh` (still pointed at the
shipping g90) need to be re-pointed at the offline
g90's IP. Then:
1. Update the IP in those wrappers
2. SSH in, follow the "First-time setup" steps above
3. The Update button on the launcher's bottom row will
   pull the latest code on demand.
