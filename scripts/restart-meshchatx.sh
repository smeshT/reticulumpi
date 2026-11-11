#!/bin/bash
# restart-meshchatx: restart the Reticulum stack in dependency order.
#
# Called by BOTH the launcher's "MeshChat Restart" button (via
# restart-meshchatx.sh) and the wifi captive portal's "Restart MeshChatX"
# button. There used to be two different scripts with the same name doing
# different things -- the portal version never restarted rnsd, the launcher
# version did but left lxmd stopped. This is the single reconciled copy.
#
# ORDER IS THE WHOLE POINT:
#   1. stop lxmd       - it must not race rnsd to the @rns/default socket
#   2. restart rnsd    - reloads interfaces from config; this is the master
#   3. wait for rnsd   - a client started against a dead socket never
#                        attaches, and never retries on its own
#   4. restart meshchatx
#   5. start lxmd      - BindsTo= does not re-trigger on restart, so an
#                        explicit start is required after a rnsd bounce
#
# Leaving step 5 out is what made the g90digi PN vanish for five weeks:
# every button press stopped lxmd and never brought it back.

set -e

RNSD_SVC="reticulumhf-rnsd.service"
CHAT_SVC="meshchatx.service"
LXMD_SVC="lxmd.service"

# sudo -n: never prompt. A launcher HTTP handler has no TTY, so a password
# prompt would hang the request until the browser times out.
SUDO="sudo -n"

# Clear any failed state so a restart is not blocked by the rate limiter.
$SUDO systemctl reset-failed "$RNSD_SVC" "$CHAT_SVC" "$LXMD_SVC" 2>/dev/null || true

# --- 1. stop lxmd so it cannot beat rnsd to the shared instance -------------
$SUDO systemctl stop "$LXMD_SVC" 2>/dev/null || true

# --- 2. stop any stray meshchatx process -----------------------------------
# `|| true` is required: pkill exits 1 when nothing matches, and under
# `set -e` that would abort the script before rnsd is ever restarted.
pkill meshchatx 2>/dev/null || true

# --- 3. restart rnsd (reloads interfaces from config) ----------------------
$SUDO systemctl restart "$RNSD_SVC"

# --- 4. wait for rnsd to be fully up ---------------------------------------
# Bounded: 30s then give up rather than hang the HTTP request forever.
_n=0
until $SUDO systemctl is-active --quiet "$RNSD_SVC"; do
    sleep 0.2
    _n=$((_n + 1))
    if [ "$_n" -ge 150 ]; then
        echo "restart-meshchatx: $RNSD_SVC did not become active in 30s" >&2
        exit 1
    fi
done
# Small settling window: is-active goes true slightly before the socket
# is actually accepting clients.
sleep 0.5

# --- 5. restart meshchatx --------------------------------------------------
$SUDO systemctl restart "$CHAT_SVC"

# --- 6. start lxmd ---------------------------------------------------------
# Explicit start: BindsTo= keeps lxmd tied to rnsd's lifetime, but does not
# restart it when rnsd is restarted. Without this line lxmd stays down and
# the propagation node silently disappears.
$SUDO systemctl start "$LXMD_SVC"

# --- 7. verify -------------------------------------------------------------
sleep 3
_rc=0
for _svc in "$CHAT_SVC" "$LXMD_SVC"; do
    if $SUDO systemctl is-active --quiet "$_svc"; then
        echo "$_svc active"
    else
        echo "$_svc FAILED to come up" >&2
        $SUDO journalctl -u "$_svc" --no-pager -n 10 >&2 || true
        # lxmd under --service logs to ~/.lxmd/logfile, NOT the journal,
        # so journalctl above will be nearly empty. Show the real log too.
        if [ "$_svc" = "$LXMD_SVC" ] && [ -f "$HOME/.lxmd/logfile" ]; then
            echo "--- ~/.lxmd/logfile ---" >&2
            tail -20 "$HOME/.lxmd/logfile" >&2 || true
        fi
        _rc=1
    fi
done

exit "$_rc"
