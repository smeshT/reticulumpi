#!/bin/bash
# toggle_modem73_audio.sh — Enable or disable the Modem73 OFDM modem in
# Reticulum on the g90test box, without taking rnsd or reticulum-meshchat
# down.
#
# Pattern source: toggle_freedv_audio.sh on sbitx, with the freedvtnc2
# references replaced by modem73 (which is a detached subprocess, not
# a systemd service).

set -u

CONFIG="/home/pi/.reticulum/config"
RNSD="reticulumhf-rnsd.service"
PARSER="/home/pi/shared_launcher/scripts/parse_modem73_block.awk"
START_SCRIPT="/home/pi/shared_launcher/scripts/start_modem73_loopback.sh"
STOP_SCRIPT="/home/pi/shared_launcher/scripts/stop_modem73_loopback.sh"

die() { echo "toggle_modem73_audio: $*" >&2; exit "$2"; }

# Verify sudo -n works for systemctl without password.
if ! sudo -n true 2>/dev/null; then
    die "sudo -n unavailable; passwordless sudo required for this script" 3
fi

[ -f "$CONFIG" ]  || die "$CONFIG not found" 1
[ -f "$PARSER" ]  || die "$PARSER not found" 1
[ -x "$START_SCRIPT" ] || die "$START_SCRIPT not executable" 3
[ -x "$STOP_SCRIPT" ]  || die "$STOP_SCRIPT not executable" 3

# ---------- find current state ----------
get_state() {
    awk -f "$PARSER" "$CONFIG"
}

current=$(get_state) || die "could not find enabled= inside [[Modem73]] block (and no [[Modem73]] block exists to create — check the awk parser)" 1

# ---------- determine target state ----------
target="${1:-}"
case "$target" in
    on|true|1)  target=true ;;
    off|false|0) target=false ;;
    "")
        if [ "$current" = "true" ]; then target=false; else target=true; fi
        ;;
    *) die "unknown argument: $target (use: on | off)" 3 ;;
esac

echo "current: enabled = $current"
echo "target:  enabled = $target"

# ---------- edit the config atomically ----------
python3 - "$CONFIG" "$target" <<'PYEOF'
import sys, re, pathlib
cfg_path, new_val = sys.argv[1], sys.argv[2]
p = pathlib.Path(cfg_path)
text = p.read_text()

m_start = re.search(r'^\s*\[\[(?i:Modem73)\]\]', text, re.MULTILINE)
if not m_start:
    # The Modem73 interface block doesn't exist in the config (fresh
    # install: the bootstrap didn't create it, and the ReticulumHF
    # wizard doesn't add it). Create a default block at the end of
    # the file. Pattern matches the g90digi config: type=Modem73Interface,
    # target_port=8002, control_port=8073, mode=roaming (to rate-limit
    # per-interface announces; full internal mode causes cross-box
    # announce cascades on the g90 fleet).
    block_template = (
        '\n[[Modem73]]\n'
        '  type = Modem73Interface\n'
        '  enabled = ' + new_val + '\n'
        '  target_host = 127.0.0.1\n'
        '  target_port = 8002\n'
        '  control_host = 127.0.0.1\n'
        '  control_port = 8073\n'
        '  mode = roaming\n'
        '  announce_cap = 1\n'
    )
    if not text.endswith('\n'):
        block_template = '\n' + block_template
    tmp = p.with_suffix('.config.toggle.tmp')
    tmp.write_text(text + block_template)
    tmp.replace(p)
    print('created [[Modem73]] block with enabled = ' + new_val)
    sys.exit(0)
start = m_start.start()
rest = text[m_start.end():]
m_nxt = re.search(r'\n\s*\[\[', rest)
end = m_start.end() + (m_nxt.start() if m_nxt else len(rest))

block = text[start:end]
new_block, n = re.subn(
    r'(?m)^(\s*)#.*$|^(\s*)enabled\s*=[^\n]*',
    lambda mm: (mm.group(0) if mm.group(2) is None
                else mm.group(2) + 'enabled = ' + new_val),
    block,
    count=1,
)
if n != 1:
    sys.exit('expected 1 enabled= in [[Modem73]] block, found ' + str(n))

new_text = text[:start] + new_block + text[end:]
tmp = p.with_suffix('.config.toggle.tmp')
tmp.write_text(new_text)
tmp.replace(p)
print('config updated: ' + str(n) + ' replacement(s)')
PYEOF
[ $? -eq 0 ] || die "config edit failed" 1

# ---------- act on the new state ----------
if [ "$target" = "true" ]; then
    pkill js8call  2>/dev/null
    pkill wsjtx    2>/dev/null
    pkill fldigi   2>/dev/null
    pkill pavucontrol 2>/dev/null
    sleep 1
    "$START_SCRIPT" || die "start_modem73_loopback.sh failed" 2
else
    "$STOP_SCRIPT" || die "stop_modem73_loopback.sh failed" 2
fi

# Always bounce rnsd so it picks up the config change.
if ! sudo -n systemctl restart "$RNSD"; then
    die "systemctl restart $RNSD failed" 2
fi

echo "done: modem73 interface is now $([ "$target" = "true" ] && echo enabled || echo disabled) in Reticulum"
exit 0
