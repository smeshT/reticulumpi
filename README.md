# reticulumpi

<img width="937" height="888" alt="Screenshot from 2026-09-10 10-01-10" src="https://github.com/user-attachments/assets/34044319-720a-46a2-9af4-cb7a1ad74951" />


## Pre-built image (recommended)

Download the latest captured image and flash it directly. 

**Latest:** `v1.0.0` — 2026-09-11
- Image: [reticulum-pi-2026-09-11-base.img.xz](https://github.com/smeshT/reticulumpi/releases/download/v1.0.0/reticulum-pi-2026-09-11-base.img.xz) (876 MB)
- Manifest: [reticulum-pi-2026-09-11-base.manifest.json](https://github.com/smeshT/reticulumpi/releases/download/v1.0.0/reticulum-pi-2026-09-11-base.manifest.json)
- MD5: `075c5515773087376260147ef2c4f961`
- SHA256: `27e8e7fc44485d83de13fc5e17aacafb82cb33177e66c3759ce6b2ab9a8dc031`

**Flash instructions:**

1. **Download** the `.img.xz` file (about 876 MB).
2. **Flash** with Raspberry Pi Imager (any OS) or `dd` on Linux:
   - **Pi Imager:** choose "Use custom image" → select the `.img.xz` file directly. Imager decompresses automatically.
   - **Linux dd:** `xzcat reticulum-pi-2026-09-11-base.img.xz | sudo dd of=/dev/sdX bs=4M status=progress conv=fsync` (replace `/dev/sdX` with your SD card or USB drive).
4. **Boot** the Pi. First boot takes ~2-3 minutes.
5. **Connect**
   - Ethernet cable to router.
      - If using a USB wifi dongle, this can now be configured the network with the "Wifi" button on the Web launcher
page above.
   - Or; AP wifi. The Pi broadcasts `ReticulumPi` (password `reticulumpi`) by default. This allows for a direct
connection to pi without a wifi or LAN network.
6. **Use**
   - Web launcher: http://reticulumpi.local/
   - SSH: `ssh pi@reticulumpi.local` — password `reticulumpi
## Build from script (advanced / dev only)

If you want to build from scratch (e.g., to customize, or to test new
launcher versions before we capture a new image), the legacy flow is
still supported:

1. Flash a fresh [ReticulumHF](https://github.com/LFManifesto/ReticulumHF/releases/tag/v1.0) image to an SD card or USB drive with Raspberry pi imager. 
  
2. Boot pi with created image and connect pi to internet access with an
ethernet cable.

**Note 1st boot will take 5+ min until ready to connect**

3. Once connected open a terminal on a connected device and copy and paste
the block below. You will be prompted to enter a password; `reticulumhf`.

``` bash
ssh pi@reticulumhf.local
curl -sSL https://raw.githubusercontent.com/smeshT/reticulumpi/main/scripts/reticulumpi-bootstrap.sh | bash
```
If you are building multiple copies you will get an SSH warning, clear with
`ssh-keygen -R reticulumpi.local`

## What's here
check [Releases](releases/README.md) for up to date list.

**Ham Apps/Modems**
- ReticulumHF web UI
- js8call
- fldigi and flrig
- WSJT-X
- Modem73
- freedvtnc2
- PAT (not working)
- Pat Menu (not working)
- ARDOP (not working)
- MeshchatX


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
