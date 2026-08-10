#!/bin/bash
# g90 askpass wrapper for ssh from the dev Pi (nomadpi).
# Used by ~/.local/bin/ssh-g90 via SSH_ASKPASS.
#
# ⚠️  2026-07-20 — the password below (6292) was leaked via
# Telegram chat (DM between @Mmsp907 and @CletusTbot). Any g90
# flashed from this image inherits the same compromised PIN.
# Action required: replace the password below with a fresh,
# unique value per box (or remove this file entirely and
# migrate to ssh keys). See memory/g90-project.md → "g90 ssh
# password leaked via Telegram" for full context.
echo "6292"
