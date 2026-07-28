# Short Turn Router — design notes (2026-07-28)

## Problem

Cletus (and other agents) were burning Ollama Cloud GPU time on short
confirmation turns ("go", "yes", "do it", "ok") that don't need a 200B-class
model. One Cletus session: 167M input tokens, 883 turns, 60-70% of which
were short confirmations.

## Solution

A `before_model_resolve` plugin that routes short turns to a small local
model (`ollama/qwen2.5:3b`, ~2GB on the Pi) and keeps heavy turns on the
primary cloud model (`minimax-m3:cloud`).

The plugin lives at `/home/pi/.openclaw/extensions/short-turn-router/`.
Symlink: `~/.openclaw/workspace/plugins/short-turn-router`.

## What the hook sees

`before_model_resolve` only receives:
- `prompt: string` — current user message
- `attachments[]` — file metadata

**No session history, no prior turns, no token counts.** This is a hard
constraint of the hook phase. The routing signal is therefore limited to
characteristics of the current message.

## Heuristic (conservative, false-negative biased)

Routes to local 3B iff:
1. No attachments
2. Prompt trimmed length ≤ `maxPromptLength` (default 40 chars)
3. Prompt matches the curated `phrases` allowlist, OR
   - is a single token ≤ 12 chars, OR
   - matches `/^do\s+\w{1,8}$/` (short "do X" imperatives)

Anything else → default model. False negatives (heavy turn routed to M3
when it could have gone to local) are accepted; false positives (short turn
routed to local when it should have stayed on M3) cost user trust.

## Configuration

Override at `plugins.entries.short-turn-router.config` in `openclaw.json`:

```json5
{
  plugins: {
    entries: {
      "short-turn-router": {
        enabled: true,
        config: {
          enabled: true,           // master toggle
          shortModel: "ollama/qwen2.5:3b",
          maxPromptLength: 40,
          phrases: ["go", "yes", "do it", ...],  // overrides default
        }
      }
    }
  }
}
```

Defaults are sensible. Don't override unless the heuristic is wrong for
your patterns.

## Companion changes (same session)

- `agents.list[cletus].contextTokens: 80000` — hard cap on input per turn
- `agents.defaults.compaction.keepRecentTokens: 20000` (was 50000)
- `agents.defaults.compaction.maxHistoryShare: 0.4` (was 0.7)
- `agents.defaults.compaction.notifyUser: true`
- `qwen2.5:3b` added to provider catalog and `agents.defaults.models`
- Meta-agent cron (weekly audit of unused features)

## Why local 3B not cloud m2.7

Ollama Pro is GPU-time-based, not token-based. Routing short turns to a
smaller cloud model still bills Ollama, just less. Local 3B is the binary
win: short turns cost zero Ollama GPU time.

Also: the routing infrastructure is the same code path that will run when
the Strix Halo arrives. Building it now means the upgrade is a config
change, not a rewrite.

## Expected impact

For a session like Cletus's (167M input, 60-70% short turns):
- Before: 167M input to M3 cloud
- After compaction: ~50-80M input to M3 cloud (heavy turns only)
- After routing: ~20-30M input to M3 cloud (heavy turns only, routed)

Net: ~85% reduction in Ollama GPU time for the same work.

## Verification

Tested with isolated short prompts in the main session:
- "go" → routed to qwen2.5:3b (asked for clarification since no prior context)
- "ok" → routed to qwen2.5:3b (correctly noted no pending task)
- Substantive question → routed to M3 (web search, full reasoning)

Routing is working. Real validation needs to come from watching a Cletus
session over the next day or two.

## Forced compaction of Cletus's 167M-token session

2026-07-28 16:47 — session was at 303k/524k (58%) but the cumulative
turns/turn-cost was 167M tokens. The LLM-summarization path timed out
(180s default not enough for 167M tokens). Used `--max-lines 200`
truncation instead:

```
openclaw sessions compact "agent:cletus:telegram:direct:5076902913" \
  --agent cletus --max-lines 200 --timeout 600000
```

Result: 5.6MB / 1771 lines / 167M tokens → 773KB / 200 lines / ~20-30k
tokens. Original archived as `.bak.2026-07-28T22-47-44.677Z`.

Trade-off: this is a *truncation*, not a *summarization*. The model
loses the older half of the session context. For Cletus's active bridge
debug, that's OK because the relevant work is in the last 200 lines. For
cases where the older context matters, use the LLM-summarization path
with a longer timeout (or schedule it for low-traffic hours).

The CLI hint about `--max-lines` is documented but the default-messaging
in docs leads with LLM summarization. Truncation is the right tool when
the session is mostly confirmations and the recent tail has the work.