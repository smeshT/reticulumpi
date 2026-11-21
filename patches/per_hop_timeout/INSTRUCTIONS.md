# Fixing HF links after an RNS upgrade — plain instructions

You do not need to understand Reticulum internals to run this. If your HF links
suddenly started failing where they used to work, and you recently ran
`pipx upgrade rns` or `pipx upgrade reticulum`, this is almost certainly why.

Read the section matching how much you want to do.

---

## What broke, in one paragraph

Reticulum gives a link a limited time to establish. By default that limit is
**6 seconds per hop**, which is fine for LoRa and TCP and far too short for HF
at 100-300 bits per second. On a slow radio link, the request and reply can
take two minutes, so the default gives up long before the other station answers.

This patch lets one interface (your slow HF one) use a longer limit while every
other interface on the same machine keeps the fast default. Without it, or with
it reverted, HF links fail with no error message — the log looks clean and the
link simply never comes up.

**The upgrade deleted the patch.** It has to be put back after every upgrade.

---

## Step 1 — see whether the patch is present

Run this. It changes nothing:

```bash
bash ~/.reticulum/interfaces/per_hop_timeout/verify_per_hop_timeout.sh
```

It prints one line per piece of the patch.

- **`RESULT: patched`** — nothing to do. Stop here.
- **`RESULT: REVERTED`** — continue to Step 2.
- **`ERROR: RNS package not found`** — the script could not find RNS. Pass your
  environment path explicitly:
  `bash verify_per_hop_timeout.sh ~/.local/pipx/venvs/rns`

If you are unsure which environment runs Reticulum, this prints the path:

```bash
readlink -f "$(which rnsd)"
```

`.../venvs/rns/bin/rnsd` means the environment is `.../venvs/rns`.

---

## Step 2 — put the patch back

```bash
python3 ~/.reticulum/interfaces/per_hop_timeout/install.py
```

That is the whole command. It finds the RNS package, backs up every file it
touches, applies the change, checks the result compiles, and restores the
backups if anything goes wrong.

Then restart Reticulum:

```bash
sudo systemctl restart rnsd
```

**If you also run `lxmd`**, it has its own separate copy of Reticulum and needs
the same treatment with its own environment:

```bash
python3 ~/.reticulum/interfaces/per_hop_timeout/install.py \
    --venv ~/.local/pipx/venvs/lxmf
sudo systemctl restart lxmd
```

---

## Step 3 — confirm it took

Use the same Python that runs Reticulum, **not** the system `python3`. The
system interpreter cannot see RNS, and will fail with
`ModuleNotFoundError: No module named 'RNS'`.

Run this **single line**. Copy it exactly; it is one command, not a heredoc:

```bash
~/.local/pipx/venvs/rns/bin/python -c "from RNS.Link import Link; print('per-hop:', Link.ESTABLISHMENT_TIMEOUT_PER_HOP, 'helper:', hasattr(Link,'per_hop_timeout_for'))"
```

Expected after a successful install:

```
per-hop: 6 helper: True
```

**The timeout value is not what proves the patch worked.** It is `6` on a stock
global constant, `120` or `240` if an older patch hardcoded it — any of those is
fine. **`helper: True` is the actual test.**

If you get `ModuleNotFoundError`, you used the wrong interpreter. Find the
right one with:

```bash
head -1 "$(readlink -f "$(which rnsd)")"
```

That prints the interpreter path, which you can use directly.

---

## Step 4 — make sure your config asks for it

The patch only provides the mechanism. Your HF interface has to request the
longer limit in `~/.reticulum/config`:

```ini
[[Your HF Interface Name]]
    type = Modem73Envelope
    per_hop_timeout = 240
```

240 means 240 seconds per hop, so a two-hop path gets 480 seconds. Adjust to
suit your link; 240 is a reasonable starting point for HF at a few hundred bits
per second.

**An interface without this line keeps the stock 6 seconds.** That is the point
of the design: only the interface you name is slowed down.

---

## If you would rather do it by hand

The script does three edits. Any competent user can reproduce them.

**1. `RNS/Link.py`** — find the line defining the timeout:

```python
ESTABLISHMENT_TIMEOUT_PER_HOP = RNS.Reticulum.DEFAULT_PER_HOP_TIMEOUT
```

**Leave that line alone.** Immediately *below* it, add this method:

```python
    @staticmethod
    def per_hop_timeout_for(interface):
        value = getattr(interface, "per_hop_timeout", None)
        if value is None:
            return Link.ESTABLISHMENT_TIMEOUT_PER_HOP
        return value
```

**2. `RNS/Link.py`** — find the two places that use the constant and route them
through the helper:

```python
# responder
link.establishment_timeout = (Link.per_hop_timeout_for(
    getattr(packet, "receiving_interface", None)) * max(1, packet.hops) + Link.KEEPALIVE)

# initiator
self.establishment_timeout += Link.per_hop_timeout_for(
    _first_hop_interface) * max(1, RNS.Transport.hops_to(self.destination.hash))
```

**3. `RNS/Interfaces/Interface.py`** — in `__init__`, add the default:

```python
self.per_hop_timeout = None
```

**4. Your own interface file** in `~/.reticulum/interfaces/` — read the key and
assign it, because Reticulum does not pass config to interfaces generically:

```python
per_hop_timeout = int(c["per_hop_timeout"]) if "per_hop_timeout" in c else None
...
super().__init__(owner, c)
self.per_hop_timeout = per_hop_timeout
```

Then:

```bash
python3 -m py_compile <each edited file>
sudo systemctl restart rnsd
```

**Step 4 is the one people miss.** The patch can be perfectly installed and do
nothing at all if the interface never reads the key.

---

## Undoing it

```bash
python3 ~/.reticulum/interfaces/per_hop_timeout/install.py --revert
```

This restores the most recent backup of each file. To undo by hand, remove the
helper method, put the original two lines back, and restart `rnsd`.

---

## Why this cannot just live in `~/.reticulum/interfaces/`

Reticulum looks in `~/.reticulum/interfaces/` for **interface classes** — files
named by their `type =` in the config. It does not look there for core modules.

`RNS.Link` is imported from inside the installed package, so a `Link.py` sitting
in your interfaces directory **is never loaded**. It looks meaningful and does
nothing. That is why the installer copies the change into the package itself,
and why the patch must be re-applied after every upgrade.

---

## Keeping it applied automatically

If you upgrade often, run the installer from a systemd drop-in or a cron
`@reboot` job so it re-applies itself. Example, as a drop-in for `rnsd`:

```ini
# /etc/systemd/system/rnsd.service.d/10-per-hop-timeout.conf
[Service]
ExecStartPre=/usr/bin/python3 /home/YOURUSER/.reticulum/interfaces/per_hop_timeout/install.py --quiet
```

Then `sudo systemctl daemon-reload`. The installer exits 0 whether or not a
change was needed, so it is safe to run every start.

---

## What this patch does not fix

**It does not make a dead peer answer faster.** It only gives a slow peer enough
time. If the path is stale or the radio is off frequency, a longer timeout makes
the failure take longer, not succeed. A 240 s budget at two hops means up to
eight minutes before the client gives up. If you see a hang instead of a quick
failure, that is the cost of this trade, and you can lower the value.

**It does not affect `fwdsvc`.** That is a separate Go program with its own
Reticulum implementation and its own timing constants.

**It is not in upstream Reticulum.** After an upgrade you must re-apply it, and
nothing in the log will tell you if you forget.

---

## Files in this directory

| File | Purpose |
|---|---|
| `install.py` | Copies these changes into the installed RNS package |
| `verify_per_hop_timeout.sh` | Reports whether the patch is present. Changes nothing |
| `README.md` (one level up) | Technical detail, rationale, measurements |
| `INSTRUCTIONS.md` | This file |
