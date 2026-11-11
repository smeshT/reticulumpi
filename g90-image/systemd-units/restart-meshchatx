#!/bin/bash
# restart-meshchatx: restart the Reticulum stack in g90digi's proven order.
#
# Mirrors the live g90digi behaviour exactly:
#     stop lxmd  ->  restart rnsd  ->  wait  ->  restart meshchatx  ->  start lxmd
#
# Called by the launcher's "MeshChat Restart" button AND (via
# /usr/local/bin/restart-meshchatx) the wifi captive portal's "Restart
# MeshChatX" button. Those used to be two different scripts of the same name
# doing different things -- the portal version never restarted rnsd, and the
# launcher version stopped lxmd without restarting it. One implementation now.
#
# WHY THE ORDER MATTERS:
#   * lxmd must be stopped first. It is a client of the @rns/default shared
#     instance; if it beats rnsd to the socket, rnsd fails to load interfaces
#     from config.
#   * rnsd restarts next and must be fully up before any client starts. A
#     client launched against a dead socket never attaches and does not
#     retry on its own.
#   * lxmd is started explicitly at the end. BindsTo= means lxmd dies with
#     rnsd, but it does NOT restart lxmd when rnsd is restarted -- so an
#     explicit start is required, or the propagation node silently vanishes.
#     That omission is what made g90digi's PN disappear for five weeks.
#
# zerotier-one.service is deliberately NOT restarted. It is how deployed
# boxes are reachable; bouncing it mid-update drops the operator's transport.

set -e

RNSD_SVC="reticulumhf-rnsd.service"
CHAT_SVC="meshchatx.service"
LXMD_SVC="lxmd.service"

# sudo -n: never prompt. Under an HTTP handler there is no TTY, so a password
# prompt would hang the request until the browser gives up.
SUDO="sudo -n"

# Clear any failed rate-limiter state so the restart is not blocked.
$SUDO systemctl reset-failed "$RNSD_SVC" "$CHAT_SVC" "$LXMD_SVC" 2>/dev/null || true

# --- 1. stop lxmd first: it must not race rnsd to the shared instance ------
$SUDO systemctl stop "$LXMD_SVC" 2>/dev/null || true

# --- 2. stop any stray meshchatx process -----------------------------------
# `|| true` is required: pkill exits 1 when nothing matches, and under
# `set -e` that would abort before rnsd is ever restarted.
pkill meshchatx 2>/dev/null || true

# --- 3. restart rnsd (reloads interfaces from config) ----------------------
$SUDO systemctl restart "$RNSD_SVC"

# --- 4. wait for rnsd to be fully up ---------------------------------------
# Bounded at 30s so a wedged rnsd cannot hang the HTTP request forever.
_n=0
until $SUDO systemctl is-active --quiet "$RNSD_SVC"; do
    sleep 0.2
    _n=$((_n + 1))
    if [ "$_n" -ge 150 ]; then
        echo "restart-meshchatx: $RNSD_SVC did not become active in 30s" >&2
        exit 1
    fi
done
# is-active goes true slightly before the socket accepts clients.
sleep 0.5

# --- 5. restart meshchatx --------------------------------------------------
$SUDO systemctl restart "$CHAT_SVC"

# --- 6. start lxmd ---------------------------------------------------------
# Explicit: BindsTo= does not re-trigger on a rnsd restart. Without this the
# propagation node stays down and nothing reports it.
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
        # lxmd under --service logs to ~/.lxmd/logfile, NOT the journal, so
        # the journalctl above will be nearly empty. Show the real log.
        if [ "$_svc" = "$LXMD_SVC" ] && [ -f "$HOME/.lxmd/logfile" ]; then
            echo "--- ~/.lxmd/logfile ---" >&2
            tail -20 "$HOME/.lxmd/logfile" >&2 || true
        fi
        _rc=1
    fi
done

# Report the propagation node explicitly: an "active" lxmd that is not
# running a PN is the exact failure this script exists to prevent.
if $SUDO systemctl is-active --quiet "$LXMD_SVC"; then
    # Resolve the binary explicitly. lxmd lives in the pipx venv's bin dir
    # via a ~/.local/bin symlink, which is NOT on the PATH this script gets
    # (systemd/HTTP handlers get the minimal system PATH). A bare `lxmd`
    # silently fails here and the check would never run.
    _lxmd_bin=""
    for _cand in /home/pi/.local/bin/lxmd \
                 /home/pi/.local/pipx/venvs/lxmf/bin/lxmd; do
        if [ -x "$_cand" ]; then _lxmd_bin="$_cand"; break; fi
    done
    if [ -n "$_lxmd_bin" ]; then
        if ! $_lxmd_bin --status 2>/dev/null | grep -qi "Propagation Node running"; then
            echo "WARNING: lxmd is active but no propagation node is running" >&2
            echo "  check ExecStart flags: systemctl show lxmd.service -p ExecStart" >&2
            _rc=1
        fi
    else
        echo "NOTE: lxmd binary not found; skipped propagation node check" >&2
    fi
fi

exit "$_rc"
