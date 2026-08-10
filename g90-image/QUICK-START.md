# g90 Quick Start

_A printed sheet for the new owner of the g90digi box._

## What this is

A small black box (Raspberry Pi 4) that runs a digital
amateur radio control panel. It broadcasts its own wifi
network so you can configure it from a phone. The Pi
itself doesn't need internet — it talks to the radio
over USB.

## First-time setup (do this once)

1. **Power on.** Plug the included USB-C power supply
   into the Pi. A red LED lights up. Wait about 60
   seconds for boot. The Pi's green activity LED will
   flicker during boot, then settle to a slow blink.

2. **Connect your phone to the Pi's wifi.** On your
   phone, open wifi settings and connect to:

   - **Network name:** `g90digi-AP`
   - **Password:** `135g90xu`

   Your phone will warn "no internet" — that's normal.
   The Pi is just a local server, not the internet.

3. **Open the control panel.** In your phone's web
   browser, go to:

   - **Main panel:** `http://192.168.4.1/` or
     `http://g90digi.local/`
   - **App launcher:** same address, port 8090 — click
     "Open Shared Launcher" on the main panel, or go
     to `http://g90digi.local:8090/` directly

   You should see a dark-themed page with rows of
   buttons for the radio apps (FLrig, JS8Call, FLDigi,
   WSJT-X, Pat Menu, etc.).

## What the buttons do

The launcher page has rows for each app. Each row has:

- **A name** (sometimes a link to a help page — tap
  to read)
- **Start** (begins the app)
- **Stop** (ends the app)

The pill at the top of the page is green when a service
is running and red when it's not. The page auto-refreshes
every 3 seconds.

Below the app rows:

- **Reticulum Stack: Start/Stop** — brings up the
  off-grid mesh network (RNS daemon, MeshChat, FreeDV
  TNC). Click Start to bring the mesh online.
- **Reset Audio Devices** — restarts the audio stack
  if apps can't find the sound card. Takes the mesh
  down briefly; click Reticulum Stack: Start to bring
  it back.
- **Wifi** — links to the wifi setup page (the one
  you used to get here).
- **Old Apps** — the original app control page.
- **Reboot** — restarts the Pi (~60s downtime).
- **Shutdown** — powers off the Pi. You'll need to
  physically unplug and replug power to bring it back
  up.

## If you want to use Winlink (Pat)

1. In the launcher, click **Pat Menu: Start**. This
   brings up the pat web UI (a separate browser tab
   opens automatically).
2. To send a message over the radio, plug in the G90
   (or your radio of choice) via USB BEFORE clicking
   Pat Menu: Start. The radio's USB audio + serial port
   need to be present or pat will fail to find the
   modem.
3. **Important:** the callsign is currently `N0CALL` —
   you must change it before sending. In the launcher,
   open the yad menu (Pat Menu: Start also opens a
   yad in the noVNC tab) → Settings → Current Config
   Settings → Call Sign → save.

## If you have problems

- **Page won't load?** Make sure you're on the
  `g90digi-AP` wifi, not your home wifi.
- **App button does nothing?** Check the pill at the
  top. If it's red, the service is stopped; if it
  says "failed," there's a real problem (probably no
  radio plugged in for the modem).
- **Can't connect to the Pi at all?** Power-cycle it
  (unplug, wait 10 seconds, replug). Wait 60s, then
  try again.
- **Want to use your own home wifi instead of the
  Pi's access point?** On the main panel, click
  "Scan WiFi" and connect to your home network. The
  Pi will switch to your network; you'll need to find
  its new IP address (check your router's admin page
  or use a network scanner app like Fing).

## Important notes

- **Do not unplug power while the green LED is
  flickering fast.** That means the SD card is being
  written to (logs, settings). Wait for the slow
  blink first.
- **The Pi runs 24/7** is fine — it's designed for
  that. Just make sure it has airflow; the case gets
  warm under load.
- **The Pi has a UPS battery (Waveshare HAT).** If
  power goes out, it runs for a while on battery. The
  brown battery indicator on the HAT is normal — it
  means "no charging active" (because mains is fine
  or because it's discharging).

## Where to get help

- **In the launcher, tap the app name** (FLrig,
  JS8Call, FLDigi, WSJT-X) — opens a help page for
  that specific app.
- **For everything else:** contact Jack (the original
  owner / builder of this box).

## Box details (for reference)

- **Hostname:** `g90digi`
- **AP SSID:** `g90digi-AP`
- **AP password:** `135g90xu`
- **AP IP:** `192.168.4.1`
- **Web UIs:**
  - Wifi setup: port 80 (`http://192.168.4.1/`)
  - Shared launcher: port 8090 (`http://192.168.4.1:8090/`)
  - Old apps page: port 80, `/apps` path
  - Pat web UI: port 5000, `/ui` path (only available
    after clicking Pat Menu: Start)
  - noVNC: port 6080 (for the yad menu's graphical
    interface)
  - MeshChat: port 8000 (only available after clicking
    Reticulum Stack: Start)
- **User (terminal login):** `pi`
- **User password:** *(not needed for normal use;
  the new owner shouldn't need to log into a terminal
  — the launcher is the user interface)*
