# reticulumpi

<img width="937" height="888" alt="Screenshot from 2026-09-10 10-01-10" src="https://github.com/user-attachments/assets/34044319-720a-46a2-9af4-cb7a1ad74951" />


This is a very much a work-in-progress image build for a Raspberry pi 
to allow HF digital mode comms over a wifi connection to a PC or phone. 
Built on top of Light Fighter Manifesto's ReticulumHF 
(https://github.com/LFManifesto/ReticulumHF) it adds a wifi setup page 
to connect to your wifi network (must add a USB wifi dongle to the pi) 
and an apps launcher page to start your favorite digital modem. 
Includes JS8Call, WSJT-X, FlRig, FlDigi and PATmenu (not currently 
working).On the Reticulum side it adds Meshchat to enable running your 
own node from the pi and connecting other interfaces to a central hub
rather than from the EUD. Freedvtnc2 is able to be ran as a freestanding 
keyboard chat app as well to allow direct testing of the hf transport 
medium. 
Built with much AI assistance; Openclaw and Minimax M3

## Build from script
Flash a fresh [ReticulumHF](rhf) image to an SD card or USB drive with 
Raspberry pi imager. If using a USB dongle on the pi for wifi connection
set the network SSID and password using "Apply OS customization" -->
Edit Settings.

Boot pi with created image and connect to pi (if using dongle and setup
configured prior to flash, this is automatic; or ethernet to router; or
connect to pi AP wifi connection; SSID ReticulumHF, pw reticulumhf)

**Note 1st boot will take 5+ min until ready to connect**

Once connected open a terminal and SSH in. Copy and paste the block below.

``` bash
curl -sSL https://raw.githubusercontent.com/smeshT/reticulumpi/main/scripts/reticulumpi-bootstrap.sh | bash
```


## What's here
check [Releases](releases/launcher/README.md) for up to date list.

**Ham Apps/Modems**
ReticulumHF web UI
js8call
fldigi and flrig
WSJT-X
Modem73
freedvtnc2
PAT (not working)
Pat Menu (not working)
ARDOP (not working)
MeshchatX


## Architecture

- **Pi 4 / Pi 5** (tested: Pi 4 Model B, Pi 5 2GB)
- **Wifi dongle** Optional for connecting to existing wifi network. AP
  network works with and without dongle. (Panda PAU3 tested)
- **G90 / QYT KT-8900D** radio (will work with others but untested)
- **Radio Interface** DigiRig or Xiegu CE/DE-19 (for G90) sound card (USB)
- **FTDI cable** for CAT control (USB)
- **SanDisk Ultra Fit** USB drive (28 GB minimum)

## Credits

This project stands on the shoulders of the open-source amateur
radio and mesh networking communities. Everything here is glue —
the real work lives in the projects below.

**Base layer — the ReticulumHF image:**
- [ReticulumHF](https://github.com/LFManifesto/ReticulumHF) by the
  [Light Fighter Manifesto](https://lightfightermanifesto.org/) —
  Reticulum + codec2 data modes (DATAC1/DATAC3/DATAC4) over HF
  radio, packaged as a Raspberry Pi image.
- [freedvtnc2](https://github.com/LFManifesto/freedvtnc2) (also
  LFManifesto) — FreeDV TNC. The HF data-mode modem (uses the
  codec2 family; distinct from the FreeDV voice-mode application).

**Networking stack:**
- [Reticulum (RNS)](https://github.com/markqvist/Reticulum),
  [LXMF](https://github.com/markqvist/LXMF),
  [Sideband](https://github.com/markqvist/Sideband), and
  [NomadNet](https://github.com/markqvist/NomadNet) — all by
  Mark Qvist. The off-grid mesh layer.
- [ZeroTier](https://www.zerotier.com/) — overlay networking.

**HF data modes:**
- [codec2](https://github.com/drowe67/codec2) by David Rowe
  (drowe67) — the codec family underlying freedvtnc2's
  DATAC1/DATAC3/DATAC4 modes. (FreeDV, the voice-mode app,
  is a separate project; this image uses the codec2 data
  modes via freedvtnc2, not FreeDV voice.)
- [pat](https://github.com/la5nta/pat) by LA5NTA — Winlink client
  (Go).

**CAT control + hamlib:**
- [Hamlib](https://github.com/Hamlib/Hamlib) — rig control library.
- [flrig](https://github.com/w1hkj/flrig) by W1HKJ — transceiver
  control application.

**Amateur radio apps (apt-installed by the ReticulumHF base + our
overlay):**
- [fldigi](https://github.com/wizhippo/fldigi-flrig) (W1HKJ et al.)
  — digital modes.
- [WSJT-X](https://sourceforge.net/projects/wsjt/) by Joe Taylor
  (K1JT) et al. — FT8, JT9, etc.
- [JS8Call](https://github.com/JS8Call-improved) — originally by
  Jordan Sherer (KN4CRD), now maintained as JS8Call-improved.

**Operating system:**
- [Raspberry Pi OS](https://www.raspberrypi.com/software/) (Bookworm
  aarch64) — the foundation.

If we forgot you, open an issue — we fix credits faster than docs.

## License

TBD — currently experimental.
