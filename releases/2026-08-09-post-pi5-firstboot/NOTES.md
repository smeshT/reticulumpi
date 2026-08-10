# 2026-08-09 — pi5-g90digi-8-9-26 first fully-overlaid image

## What's this

`pi5-g90digi-8-9-26.img.xz` is the **first fully-overlaid image** for the
g90 / sbitx HF radio fleet. Captured live from the g90digi Pi 5 (Pi 5 2GB,
SanDisk Ultra Fit 28 GB USB drive) on 2026-08-09.

- MD5: `a20ead9a6ec7914c6c4d9f35052bd446`
- Compressed size: 987 MB
- Decompressed size: ~5.9 GB (pishrink'd from 28 GB raw)
- Architecture: dual-arch (Pi 4 + Pi 5 in 64-bit mode)

## How to flash

```bash
xzcat pi5-g90digi-8-9-26.img.xz | sudo dd of=/dev/sdX bs=4M conv=fsync status=progress
```

Replace `/dev/sdX` with your target (use `lsblk` to find it).



## Download

The `.img.xz` binary is **NOT** in github (1 GB is too large for git,
and github Releases have a 2 GB cap that's come and gone over the
years). The canonical copy lives on the dev Pi (nomadpi) at:

```
/media/pi/REMOTE/pi_images/pi5-g90digi-8-9-26.img.xz
```

MD5: `a20ead9a6ec7914c6c4d9f35052bd446`
SHA-256: `269a7fdf956f789b98f01cf6ce96d21fe36910b3bb5a5a00895dd17fe4921e9b`
Size: 987 MB compressed (~5.9 GB pishrunk / 28.7 GB raw)

### To fetch (laptop / another box on ZT / LAN)

```bash
# LAN mDNS
scp pi@g90digi.local:/media/pi/REMOTE/pi_images/pi5-g90digi-8-9-26.img.xz .

# LAN IP directly
scp pi@192.168.1.179:/media/pi/REMOTE/pi_images/pi5-g90digi-8-9-26.img.xz .

# ZeroTier IP (g90digi's ZT IP)
scp pi@10.59.42.237:/media/pi/REMOTE/pi_images/pi5-g90digi-8-9-26.img.xz .
```

Or via the dev Pi (nomadpi) direct:

```bash
scp pi@nomadpi.local:/media/pi/REMOTE/pi_images/pi5-g90digi-8-9-26.img.xz .
```

**HTTP download (ZT-only, 2026-08-10+):** if you're on ZeroTier
network `zttqh5myou`, the dev Pi now also serves these images over
HTTP. The ZT URL is published in the private companion repo
([`smeshT/g90digi`](https://github.com/smeshT/g90digi)). Public
readers don't have ZT access and should use the `scp` paths above.

After download, verify:

```bash
md5sum pi5-g90digi-8-9-26.img.xz
# expected: a20ead9a6ec7914c6c4d9f35052bd446

# Or SHA-256 (stronger):
sha256sum pi5-g90digi-8-9-26.img.xz
# expected: 269a7fdf956f789b98f01cf6ce96d21fe36910b3bb5a5a00895dd17fe4921e9b
```

## What's in the overlay

See `g90-image/` (this repo) for the live overlay. The captured image
applies that overlay on top of the ReticulumHF base (the parent image).

## First boot

1. Plug the USB drive / SD card into a Raspberry Pi 4 or Pi 5 (64-bit only)
2. Power on. Boots, expands rootfs to fill drive, reboots (~30 seconds)
3. After reboot, the box is online:
   - LAN: DHCP, mDNS `g90digi.local` (default — operators should rename)
   - WiFi AP: SSID `g90digi` (default), pw `<set at deploy>`
   - Captive portal: `http://192.168.4.1/` (when on AP)
   - Shared launcher: `http://g90digi.local:8090/`

## Default user/password

Both SSH and WiFi password defaults can be customized by the operator
BEFORE flashing. The bundled defaults are:

- User: `pi`
- Password: `hfp123` (CHANGE THIS on first boot!)

## Known issues

- **Default `pi` password `hfp123` is in the image.** This is a
  public-release baseline. Operators must `sudo passwd pi` on first
  boot and ideally migrate to SSH keys.
- **Default AP password is `CHANGE_ME` (placeholder).** Operators
  should edit `g90-image/config/hostapd.conf` and
  `g90-image/config/reticulumhf-config.env` before flashing, or set
  the AP password at first boot via the captive portal.
- **ZeroTier is NOT pre-configured.** Operators add their own ZT
  network via `smeshT/g90digi/etc-captures/<box>/<...>` instructions.

## Source

Captured from `g90digi.local` (Pi 5 2GB, SanDisk Ultra Fit USB drive)
via `dd if=/dev/sda | pishrink -Z`. See `NOTES.md` at the top of this
repo for the full derivation history.
