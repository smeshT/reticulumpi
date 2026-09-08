#!/bin/bash
# prepare-meshchatx-dirs.sh — create the directories meshchatx.service
# declares in ReadWritePaths so systemd can bind-mount them at startup.
#
# Why this exists:
#   meshchatx.service uses ProtectSystem=strict + ReadWritePaths to
#   sandbox what meshchatx can write to. systemd bind-mounts those
#   paths into the unit's mount namespace. If a ReadWritePaths target
#   doesn't exist on disk, systemd tries to mkdir it under
#   /run/systemd/unit-root/<path> and fails with NAMESPACE status 226.
#
# What this does:
#   mkdir /home/pi/meshchatx-storage   (meshchatx --storage-dir)
#   mkdir /home/pi/.reticulum-meshchatx (default log directory)
#
# Idempotent. Safe to run on every boot or as part of the image-overlay
# install. Run BEFORE systemctl enable meshchatx.service.
set -e
mkdir -p /home/pi/meshchatx-storage
chown pi:pi /home/pi/meshchatx-storage
mkdir -p /home/pi/.reticulum-meshchatx
chown pi:pi /home/pi/.reticulum-meshchatx
echo "meshchatx dirs ready: /home/pi/meshchatx-storage, /home/pi/.reticulum-meshchatx"
