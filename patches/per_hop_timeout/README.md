# `per_hop_timeout` — per-interface link establishment timeout

Optional config key so one interface can wait for a slow HF link while every
other interface on the same host still fails fast.

Status: **not yet applied to any host.** Written 2026-11-20.

---

## The problem

`Link.py` computes a link establishment budget in two places:

```python
# Link.py:310 — initiator
self.establishment_timeout  = get_first_hop_timeout(dest)
self.establishment_timeout += Link.ESTABLISHMENT_TIMEOUT_PER_HOP * max(1, hops)

# Link.py:214 — responder
link.establishment_timeout = Link.ESTABLISHMENT_TIMEOUT_PER_HOP * max(1, hops) + Link.KEEPALIVE
```

`ESTABLISHMENT_TIMEOUT_PER_HOP` is `6` (`RNS.Reticulum.DEFAULT_PER_HOP_TIMEOUT`),
sized for packet radio.

The `first_hop_timeout` half **is** adaptive — it multiplies `RNS.Reticulum.MTU`
by the next-hop interface's real bitrate. Measured live on sbitx 2026-11-20:

```
[17:28:55] [Info] Modem73Interface[Modem73 Callsign]: bitrate  88 ->  75 (CSMA-aware)
[17:30:20] [Info] Modem73Interface[Modem73 Callsign]: bitrate 127 -> 152 (CSMA-aware)
[17:33:50] [Info] Modem73Interface[Modem73 Callsign]: bitrate 152 -> 157 (CSMA-aware)
```

At 100 bps and MTU 500 that half yields `500 * (8/100) + 6 = 46 s`.
The observed successful link had RTT **120.7 s**, so the adaptive half is not
enough. The missing latency is propagation, tuning and CSMA backoff — none of
which bitrate models.

So the flat `6 * hops` term is the whole margin, and raising it globally
(`ESTABLISHMENT_TIMEOUT_PER_HOP = 240`, which is what sbitx and g90digi run
today) makes every LoRa and TCP interface on the same box take minutes to
report a dead peer.

---

## What this patch does

Adds `per_hop_timeout` as an **optional, per-interface** key.

```ini
[[Modem73 Callsign]]
    type = Modem73Envelope
    per_hop_timeout = 240
```

Absent → falls back to the global constant. Existing configs are unaffected.

### Files touched

| File | Change |
|---|---|
| `RNS/Interfaces/Interface.py` | default attribute `self.per_hop_timeout = None`, plus an `apply_per_hop_timeout(c)` helper |
| `RNS/Link.py` | one static helper + two call sites |
| `~/.reticulum/interfaces/Modem73Interface.py` | **per host, by hand** — reads the key and assigns it |

### Why `Modem73Interface.py` is a manual step

`Interface.__init__` takes **no configuration argument**, and stock Reticulum has
no generic per-interface key loop — every interface type reads its own keys
explicitly. So a config key is only honoured by a type that explicitly looks for
it. `Modem73Interface` now does:

```python
per_hop_timeout = int(c["per_hop_timeout"]) if "per_hop_timeout" in c else None
...
super().__init__(owner, c)
self.per_hop_timeout = per_hop_timeout
```

**Other interface types (RNode, KISS, plain TCP) will not honour the key until
they get the same two lines.** That is a deliberate consequence of the design:
the key is opt-in per type, so nothing changes for types that don't read it.

### Why the helper reads the next-hop interface rather than the config block

The initiator builds a link before it has an `attached_interface` — that is only
assigned when the LRPROOF arrives. But the path table already knows which
interface will carry the first hop:

```python
# Transport.py:3501 — exists in stock RNS, public, lock-protected
@staticmethod
def next_hop_interface(destination_hash):
    with Transport.path_table_lock:
        if   destination_hash in Transport.path_table:
            return Transport.path_table[destination_hash][IDX_PT_RVCD_IF]
        elif destination_hash in Transport.destinations_map:
            return RNS.Reticulum.get_instance().shared_instance_interface
        else:
            return None
```

`get_first_hop_timeout` already traverses this same path, so nothing new is
introduced.

---

## Applying

```bash
# inspect first
python3 apply_per_hop_timeout.py --dry-run

# then, per host (run as the user that owns the venv)
python3 apply_per_hop_timeout.py --apply
sudo systemctl restart rnsd
```

The script refuses to run unless every edit matches **exactly once**, backs up
with a timestamp, runs `py_compile`, restores on failure, prints a diff count
and the resulting lines verbatim, and clears stale `Link` bytecode.

Then add the key to the HF interface block in `~/.reticulum/config`.

---

## After an upgrade

`pipx upgrade reticulum` re-installs the wheel and the patch disappears with no
notice. Verify:

```bash
bash verify_per_hop_timeout.sh
```

Exit 0 = patched, 1 = reverted. **A missed re-apply is invisible at runtime** —
`rnsd` starts clean and links simply fail more often. That is why the verify
script exists; the patch alone does not protect you.

---

## Per-host state

| Host | venv that needs it | why |
|---|---|---|
| sbitx `.196` | `rns` (`rnsd`) | owns the HF modem; initiator in the field |
| g90digi `.237` | `rns` (`rnsd`) | same |
| g90digi `.237` | `lxmf` (`lxmd`) | separate Python process, own RNS copy |
| m5boss | `rns` | only if `fwdsvc` traffic egresses via local `rnsd` |

The `lxmf` venv carries its own copy of `RNS` and is **not** affected by
patching the `rns` venv. Both must be patched on a host that runs `lxmd`.

---

## Limits — what this does not fix

- **`fwdsvc` is unaffected.** It is Go (`thatSFguy/reticulum-group-chat`, using
  `thatSFguy/reticulum-go v0.8.1`) with its own stack. Its equivalent knobs are
  `rns.DefaultLinkSendTimeout = 30s` and `lxmf.DefaultDeliveryProofTimeout = 15s`,
  settable per-instance but **not exposed in `config.toml`**. Needs a separate
  fork.
- **Responder path is already safe.** `+ KEEPALIVE` (360 s) dwarfs any
  per-hop difference, so the responder edit is for consistency, not necessity.
- **Re-apply per venv per host.** Four places on three hosts at most.
- **Not upstream yet.** The change is additive and backwards compatible, and
  it uses only public existing API, so it is a plausible PR.
