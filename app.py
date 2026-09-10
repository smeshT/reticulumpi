from flask import Flask, render_template, redirect, url_for, request, send_file
import subprocess
import os
import re
import sys

app = Flask(__name__)

# On the real g90 boxes, the launcher lives at /home/pi/shared_launcher
# and the systemd unit is g90-shared-launcher.service. On the nomadpi's
# test sled, both are different (the work tree is on the USB stick, the
# service is g90-test-launcher.service). Override via env at startup.
LAUNCHER_DIR = os.environ.get(
    "LAUNCHER_DIR", "/home/pi/shared_launcher"
)
LAUNCHER_SERVICE = os.environ.get(
    "LAUNCHER_SERVICE", "g90-shared-launcher.service"
)

# Make the scripts/ dir importable so app.py can pull in
# config_backup without invoking it as `scripts.config_backup`
# (which would require the launcher dir on sys.path — which
# is what this line does for us, but only if it isn't
# already). 2026-09-09 21:38 MDT: v0.6.46 adds the
# backup/restore module.
if LAUNCHER_DIR not in sys.path:
    sys.path.insert(0, LAUNCHER_DIR)
from scripts import config_backup

# SCRIPTS = LAUNCHER_DIR/scripts (env-overridable for the test sled)
# so run_script() works in both /home/pi/shared_launcher (real g90)
# and /media/pi/.../g90-test-sled/work (nomadpi test sled).
SCRIPTS = os.path.join(LAUNCHER_DIR, "scripts")

# G90 VNC stack: Xvfb :1 (started by node-portal's own services), x11vnc on
# 5900, websockify on 6080. The shared launcher does NOT start its own
# desktop — the node-portal already brings up :1 and 6080. The "Open VNC
# Tab" button just links to the existing noVNC.
VNC_WS_PORT = 6080


def is_running(cmd):
    return subprocess.run(
        ["pgrep", "-f", cmd],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    ).returncode == 0


def is_running_proc_with_arg(proc_name, needle):
    """Check if a process whose name is `proc_name` (matched via
    `pgrep -x`, exact basename) is running AND has `needle` somewhere
    in its command line. This avoids the pgrep self-match bug: the
    plain `pgrep -f needle` will match its own bash wrapper, but
    `pgrep -x proc_name` matches the actual program, and then we
    look up the cmdline directly via /proc/PID/cmdline.
    """
    import os
    out = subprocess.run(
        ["pgrep", "-x", proc_name],
        capture_output=True, text=True
    ).stdout.strip()
    if not out:
        return False
    for pid in out.splitlines():
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmdline = f.read().replace(b"\x00", b" ").decode("utf-8", errors="replace")
            if needle in cmdline:
                return True
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return False




def modem73_in_reticulum():
    """Return True iff the [[Modem73]] block in
    ~/.reticulum/config has enabled = true. Drives the Modem73
    interface status pill on the launcher.

    Pattern source: freedvtnc2_in_reticulum on sbitx (which calls
    check_freedv_in_reticulum.sh). The g90 box doesn't have a
    freedvtnc2 equivalent on the launcher side; the
    freedvtnc2.service already does its own enable/disable --now
    cycle. modem73 has no systemd unit, so we drive
    enable/disable through the Reticulum config block + rnsd
    restart (handled by toggle_modem73_audio.sh).

    Implementation added on g90test 2026-09-04; promoted to the
    canonical recipe in reticulumpi 2026-09-04.
    """
    import subprocess
    try:
        out = subprocess.check_output(
            ["/home/pi/shared_launcher/scripts/check_modem73_in_reticulum.sh"],
            stderr=subprocess.DEVNULL, timeout=2,
        ).decode().strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False
    return out == "true"


def service_active(name):
    return subprocess.run(
        ["systemctl", "is-active", "--quiet", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    ).returncode == 0


def service_installed(name):
    """True iff the systemd unit file is installed on this box.

    Used to gate UI actions (Restart buttons) so a click on a box
    that doesn't have the service installed produces a visible
    error message instead of a silent `systemctl restart` failure
    that returns exit code 5 ("Unit not found").

    Distinguishes installed-but-masked from not-installed at all:
    masked services have to be unmasked first; we don't auto-do
    that, so masked counts as not-installed for our purposes.
    """
    try:
        r = subprocess.run(
            ["systemctl", "list-unit-files", "--no-legend", name],
            capture_output=True, text=True, timeout=3
        )
        if not r.stdout.strip():
            return False
        for line in r.stdout.splitlines():
            cols = line.split()
            if len(cols) >= 2 and cols[1] != "masked":
                return True
        return False
    except Exception:
        return False


def run_script(name, args=None):
    """Launch a shell script from the SCRIPTS dir as a detached child.

    Optional `args` is a list of CLI arguments to append to the
    invocation. Pattern source: sbitx's my_launcher/run_script. The
    g90 launcher (and g90test) originally only had the no-args
    form; 2026-09-04 upgrade added args support so the modem73
    toggle can pass "on" or "off" to toggle_modem73_audio.sh.
    """
    cmd = [f"{SCRIPTS}/{name}"]
    if args:
        cmd.extend(args)
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )


def systemctl(action, *services):
    """Run a systemctl action as root non-interactively. Detaches so the
    launcher's HTTP request returns immediately."""
    if action not in ("start", "stop", "restart", "reload", "enable", "disable", "reset-failed"):
        raise ValueError(f"bad systemctl action: {action}")
    subprocess.Popen(
        ["sudo", "-n", "systemctl", action, *services],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def get_lan_ip():
    """Return the box's primary LAN IPv4 address, or None if none.

    Strategy: read `hostname -I` (all non-loopback IPv4 addresses,
    space-separated) and pick the first one that isn't in the AP
    range (192.168.4.0/24) and isn't a ZeroTier address (10.0.0.0/8
    is the most common ZT range, but ZT can also use 192.168.x.x
    blocks depending on controller config — we filter both just in
    case). On the g90 box this is the eth0 DHCP address. On the
    nomadpi it's whatever the home router gave us.

    Returns None if no suitable interface is up (e.g. the box just
    booted and DHCP hasn't completed yet)."""
    try:
        out = subprocess.check_output(["hostname", "-I"], text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    for ip in out.split():
        if ip.startswith("127."):
            continue
        if ip.startswith("192.168.4."):
            # AP-only range; not the LAN
            continue
        if ip.startswith("10."):
            # Common ZeroTier range. Skip — get_zerotier_ip() handles
            # ZT display separately.
            continue
        return ip
    return None


def get_zerotier_ip():
    """Return the box's ZeroTier IPv4 address, or None if not joined
    to any ZT network.

    Strategy: list the kernel's IPv4 addresses via `ip -4 -o addr
    show` (the `-o` flag gives one-line-per-address output that's
    easy to parse), find the first interface whose name starts
    with `zt` (ZeroTier's interface-naming convention: every ZT
    interface is named `zt<10-hex-char-network-id-prefix>`), and
    return its `inet` address.

    The `ip -o` format is `INDEX: IFRNAME<spaces>INET...` — note
    only ONE colon, after the index. We split on the FIRST colon
    only and take the rest as the iface name + address data."""

    try:
        out = subprocess.check_output(
            ["ip", "-4", "-o", "addr", "show"], text=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    for line in out.splitlines():
        # "5: zttqh5myou    inet 10.59.42.91/24 ..."
        if ":" not in line:
            continue
        # Split only on the first colon
        idx, rest = line.split(":", 1)
        # Ifrname is the first whitespace-delimited token in `rest`
        ifname = rest.split()[0] if rest.split() else ""
        if not ifname.startswith("zt"):
            continue
        m = re.search(r"inet (\S+)", rest)
        if m:
            return m.group(1).split("/")[0]
    return None


def get_zerotier_network_id():
    """Return the full 16-hex-char ZeroTier network ID this box is
    a member of, or None if not joined.

    Strategy: list the contents of /var/lib/zerotier-one/networks.d/;
    each joined network has a `<nwid>.conf` file (and a sibling
    `<nwid>.local.conf` for local overrides). The full network ID
    is also stored inside the .conf file as `nwid=<hex>` on its
    first line, which is robust against future ZT versions that
    might change directory layout.

    The directory is mode 0755 zerotier-one:zerotier-one and the
    .conf files are mode 0644 — readable by any user, no privilege
    change needed.

    The .conf file's first line is `v=<protocol-version>`; the
    `nwid=<hex>` line is the second. We read the first two lines
    to find nwid and stop there because the rest of the file is
    binary-encoded state."""
    ndir = "/var/lib/zerotier-one/networks.d"
    if not os.path.isdir(ndir):
        return None
    try:
        for fn in os.listdir(ndir):
            if fn.endswith(".local.conf"):
                continue
            if not fn.endswith(".conf"):
                continue
            with open(os.path.join(ndir, fn), "rb") as f:
                head = b""
                for _ in range(3):
                    line = f.readline()
                    if not line:
                        break
                    head += line
                    if b"nwid=" in line:
                        break
            text = head.decode("utf-8", errors="replace")
            for line in text.splitlines():
                if line.startswith("nwid="):
                    return line[5:].strip()
    except (OSError, IOError):
        return None
    return None


def _get_launcher_version():
    """Return the launcher's current version tag, e.g. 'v0.3'. The
    tag is set on the bare repo at /home/pi/repos/reticulumpi.git
    with each release; `git describe --tags --abbrev=0` returns the
    most recent tag reachable from HEAD. If the working tree has
    no tag reachable (e.g. fresh clone before any tag was pushed),
    fall back to the short commit hash prefixed with 'g' so the
    template can still show *something* useful."""
    try:
        out = subprocess.check_output(
            ["git", "-C", LAUNCHER_DIR,
             "describe", "--tags", "--abbrev=0"],
            text=True, timeout=5,
        ).strip()
        if out:
            return out
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    # fallback: short commit hash
    try:
        out = subprocess.check_output(
            ["git", "-C", LAUNCHER_DIR,
             "rev-parse", "--short", "HEAD"],
            text=True, timeout=5,
        ).strip()
        if out:
            return f"g{out}"
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    return "unknown"


@app.route("/")
def index():
    # Pills are laid out left-to-right in a flex-wrap container, so
    # dict order is reading order.
    #
    # Layout (mirrors sbitx my_launcher; ordered 2026-09-04 by
    # @Mmsp907):
    #
    #   Always-on block (red flag if any of these shows "Stopped" on a
    #   healthy box):
    #     Shared Desktop -> RNSD -> MeshChat
    #   On-demand block (expect "Stopped" on a fresh boot until the
    #   operator clicks Start):
    #     digimodes (FLrig / JS8Call / FLDigi / WSJT-X) ->
    #     audio apps (Pavucontrol) ->
    #     pat pair (Pat Menu + Pat) ->
    #     freedvtnc2 TUI / Modem73 TUI ->
    #     Reticulum modems (FreeDV TNC + freedvtnc2 interface +
    #     Modem73 interface) ->
    #     Pat Menu
    #
    # FLrig replaced "Shared Desktop" / "sBitx radio" — the g90 box
    # uses flrig for its rig control, not the sbitx box's
    # AudioInjector + sbitx binary. FLrig is always-on here.
    # (g90test never boots without it either — the test sled needs
    # flrig to do any actual rig control work.)
    #
    # FreeDV TNC is green if EITHER freedvtnc2.service is active (the
    # --no-cli daemon that meshchat uses as its KISS modem) OR an
    # lxterminal running the freedvtnc2 CLI is open (the user's
    # interactive TUI in noVNC). Both bind the audio device and both
    # make the modem "up" from the user's perspective; the distinction
    # is which mode (headless vs interactive) is in use, not whether
    # the modem works.
    status = {
        # Always-on block
        "RNSD": service_active("reticulumhf-rnsd.service"),
        "MeshChatX": service_active("meshchatx.service"),
        # On-demand block
        "JS8Call": is_running("js8call"),
        "FLrig": is_running("flrig"),
        "FLDigi": is_running("fldigi"),
        "WSJT-X": is_running("wsjtx"),
        "Pavucontrol": is_running("pavucontrol"),
        #"freedvtnc2 TUI": is_running_proc_with_arg("lxterminal", "--title=freedvtnc2"),
        # The yad dialog from patmenu2 always references pmlogo.png
        # in its cmdline (the menu's logo). Earlier the pill was
        # keyed on "Pat Menu" which (a) self-matched the ssh wrapper
        # running this very code (literal "Pat Menu" in argv) and
        # (b) didn't match the actual yad cmdline when the callsign
        # was still N0CALL (title="N0CALL" then, not "Pat Menu").
        # patmenu2/pmlogo.png is present in every patmenu2 yad dialog
        # (main menu, callsign-check dialog, sub-dialogs) and is
        # not a substring of any other process on the box.
        "Pat Menu": is_running_proc_with_arg("yad", "patmenu2/pmlogo.png"),
        "Pat": service_active("pat-http.service"),
        "freedvtnc2 Chat": is_running_proc_with_arg("xterm", "-T freedvtnc2"),
        "Modem73 Config TUI": is_running_proc_with_arg("lxterminal", "--title=modem73"),
        "freedvtnc2 interface": service_active("freedvtnc2.service"),
        "Modem73 interface": modem73_in_reticulum(),
    }
    return render_template(
        "index.html",
        status=status,
        host=request.host.split(":")[0],
        vnc_ws_port=VNC_WS_PORT,
        version=_get_launcher_version(),
        lan_ip=get_lan_ip(),
        zt_ip=get_zerotier_ip(),
    )


@app.route("/start-js8call", methods=["POST"])
def start_js8call():
    run_script("start_js8call.sh")
    return redirect(url_for("index"))


@app.route("/stop-js8call", methods=["POST"])
def stop_js8call():
    run_script("stop_js8call.sh")
    return redirect(url_for("index"))


@app.route("/start-fldigi", methods=["POST"])
def start_fldigi():
    run_script("start_fldigi.sh")
    return redirect(url_for("index"))


@app.route("/stop-fldigi", methods=["POST"])
def stop_fldigi():
    run_script("stop_fldigi.sh")
    return redirect(url_for("index"))


@app.route("/start-wsjtx", methods=["POST"])
def start_wsjtx():
    run_script("start_wsjtx.sh")
    return redirect(url_for("index"))


@app.route("/stop-wsjtx", methods=["POST"])
def stop_wsjtx():
    run_script("stop_wsjtx.sh")
    return redirect(url_for("index"))


@app.route("/start-flrig", methods=["POST"])
def start_flrig():
    run_script("start_flrig.sh")
    return redirect(url_for("index"))


@app.route("/stop-flrig", methods=["POST"])
def stop_flrig():
    run_script("stop_flrig.sh")
    return redirect(url_for("index"))


@app.route("/start-pavucontrol", methods=["POST"])
def start_pavucontrol():
    run_script("start_pavucontrol.sh")
    return redirect(url_for("index"))


@app.route("/stop-pavucontrol", methods=["POST"])
def stop_pavucontrol():
    run_script("stop_pavucontrol.sh")
    return redirect(url_for("index"))


@app.route("/start-patmenu", methods=["POST"])
def start_patmenu():
    """The Pat Menu Start button is the one-click entry point for the
    full pat experience: it starts the pat-http web UI, opens the
    patmenu2 yad menu in noVNC, and the template's onsubmit opens
    the web UI in a new browser tab. So this one click does three
    things: pat-http is up, the yad menu is on the desktop, the
    Pat UI tab is in the user's phone browser.

    The web UI's port (5000) is independent of any radio, so this
    works without a G90 plugged in. With a G90 + piardopc running,
    pat will auto-detect ARDOP on :8515 and use it for outbound.

    reset-failed is called first so a previously-failed pat-http
    (e.g. from a config error) doesn't leave the service in
    systemd's rate-limited state and silently no-op the Start.
    """
    systemctl("reset-failed", "pat-http.service")
    systemctl("start", "pat-http.service")
    run_script("start_patmenu.sh")
    return redirect(url_for("index"))


@app.route("/start-freedv-tui", methods=["POST"])
def start_freedv_tui():
    """Open the FreeDV TUI in an lxterminal inside the g90 box's
    Xvfb :1 desktop (visible in the noVNC tab). The TUI runs
    freedvtnc2 --cli with the same audio/rig/KISS settings the
    daemon uses, sourced from /etc/reticulumhf/config.env.

    TUI mode and daemon mode (freedvtnc2.service) both want the
    audio device; running both simultaneously means the second
    one fails with "device busy". The sbitx box enforces this
    with Conflicts=freedvtnc2.service in the systemd unit. We
    mirror that here by stopping the daemon first if it's active.

    The script itself handles the no-radio case: if the
    configured audio device is missing, it opens the terminal
    with a clear "plug in the G90" message instead of running
    freedvtnc2. We don't add a wrapper here; the script is the
    source of truth for the UX.
    """
    if service_active("freedvtnc2.service"):
        # Stop the daemon first so freedvtnc2 --cli can grab the
        # audio device. Reset-failed so a future Start attempt
        # isn't rate-limited.
        subprocess.Popen(
            ["sudo", "-n", "systemctl", "reset-failed", "freedvtnc2.service"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        subprocess.Popen(
            ["sudo", "-n", "systemctl", "stop", "freedvtnc2.service"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    run_script("freedv_tui.sh")
    return redirect(url_for("index"))


@app.route("/stop-freedv-tui", methods=["POST"])
def stop_freedv_tui():
    """Close the FreeDV TUI xterm. Kills any xterm whose
    title is "freedvtnc2" (the script sets -T freedvtnc2).
    Using pkill on the "-T freedvtnc2" pattern is more reliable
    than pkill on the binary name alone, which would also match
    other xterms the user has open. Pattern source: 2026-09-08
    fix — the previous lxterminal-based pkill pattern matched
    no processes because the chat terminal is actually xterm
    (see memory/2026-09-08-freedv-chat-fix.md).
    """
    subprocess.Popen(
        ["pkill", "-f", "xterm.*-T freedvtnc2"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return redirect(url_for("index"))


@app.route("/stop-patmenu", methods=["POST"])
def stop_patmenu():
    """Stop the pat experience: kill the patmenu2 yad menu and
    stop pat-http. Piardopc / piARDOP_GUI are NOT touched here
    (they are managed inside the yad, when the yad is up). The
    user can close the Pat UI browser tab manually if it's still
    open."""
    run_script("stop_patmenu.sh")
    systemctl("stop", "pat-http.service")
    return redirect(url_for("index"))


@app.route("/restart-meshchatx", methods=["POST"])
def restart_meshchatx():
    """Restart MeshChatX only (not rnsd, not the legacy meshchat).

    MeshChatX is the chat client on port 8000 (was 9100 pre-2026-09-08;
    flipped to match the legacy meshchat port so existing bookmarks
    and operator muscle memory keep working). Joins rnsd's shared
    AF_UNIX instance; doesn't open its own KISS port.

    Operates the same way the old /restart-meshchat did: explicit
    `systemctl restart` bypasses Restart=on-failure and re-execs the
    unit regardless of whether systemd thought it should be running.

    If meshchatx.service isn't installed on this box (the operator
    hasn't installed the new chat client yet), we return a visible
    error page rather than silently failing — clicking Restart should
    not look successful when the underlying service is missing.

    Helper: /usr/local/bin/restart-meshchatx (also exposed for the
    wifi captive portal button). Same effect as this route, just
    invokable from the shell without going through Flask.

    Replaces the legacy /restart-meshchat (post 2026-09-08; the
    legacy meshchat was retired because MeshChatX subsumes it).
    """
    if not service_installed("meshchatx.service"):
        return (
            "<h1>MeshChatX not installed</h1>"
            "<p>The meshchatx.service unit file is not present on this "
            "box. The legacy reticulum-meshchat.service has been "
            "retired; MeshChatX replaces it.</p>"
            "<p>To install on a fleet box, see the recipe in "
            "<code>g90-image/IMAGE-PACKAGES.md</code> "
            "(meshchatx pipx venv + systemd unit + helper).</p>"
            "<p style='margin-top:2em;'>"
            "<a href='/'>Back to launcher</a></p>"
        )
    systemctl("restart", "meshchatx.service")
    return redirect(url_for("index"))


@app.route("/start-freedvtnc2-modem", methods=["POST"])
def start_freedvtnc2_modem():
    """Enable + start the freedvtnc2 KISS audio modem.

    Use this when you want the G90's audio modem active for
    Reticulum / LXMF over HF. freedvtnc2 connects to rnsd via
    TCP at 127.0.0.1:8001 (config in /etc/reticulumhf/config.env).

    enable --now so the modem comes back on reboot (per the
    ReticulumHF image's design — the modem is opt-in by default
    but persistent once activated).

    reset-failed first to clear rate-limit state from a previous
    crashloop (no G90 plugged in, audio device busy, etc.)."""
    systemctl("reset-failed", "freedvtnc2.service")
    systemctl("enable", "--now", "freedvtnc2.service")
    return redirect(url_for("index"))


@app.route("/stop-freedvtnc2-modem", methods=["POST"])
def stop_freedvtnc2_modem():
    """Disable + stop the freedvtnc2 KISS audio modem.

    disable --now so the modem stays off across reboots.
    rnsd and meshchat are unaffected — they keep running.
    Use this when switching to a different audio mode
    (js8call, fldigi, wsjtx) or to free the loopback ALSA
    device for diagnostics."""
    subprocess.Popen(
        ["sudo", "-n", "systemctl", "disable", "--now", "freedvtnc2.service"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return redirect(url_for("index"))


@app.route("/start-modem73-tui", methods=["POST"])
def start_modem73_tui():
    """Open an lxterminal running modem73 in TUI mode on the shared
    desktop. Same pattern as start-freedv-tui but for modem73.

    The script does NOT pass --device / --callsign — modem73 reads
    its saved settings from ~/.config/modem73/settings, so the
    operator's TUI-config changes (audio device, callsign) persist
    across launcher restarts.

    Conflict story (per sbitx my_launcher operator decision
    2026-09-04): the TUI mode and the loopback instance (port 8101)
    share the modem73 binary and likely config files. Don't run both
    at once — the operator's responsibility, not enforced here.
    """
    run_script("start_modem73_tui.sh")
    return redirect(url_for("index"))


@app.route("/stop-modem73-tui", methods=["POST"])
def stop_modem73_tui():
    """Close the modem73 TUI lxterminal. Same pattern as
    stop-freedv-tui: kill by --title match so we don't touch other
    lxterminals the user has open on the desktop."""
    run_script("stop_modem73_tui.sh")
    return redirect(url_for("index"))


@app.route("/start-modem73-loopback", methods=["POST"])
def start_modem73_loopback():
    """Enable the Modem73 OFDM modem in Reticulum and start the
    modem73 loopback process.

    Pattern source: sbitx /start-reticulum on the freedvtnc2 audio
    modem (toggle_freedv_audio.sh). This script does the same three
    things:
      1. Set `enabled = true` for the [[Modem73]] block in
         /home/pi/.reticulum/config (atomic edit)
      2. Start the modem73 loopback subprocess (no systemd unit —
         it's a detached child launched by start_modem73_loopback.sh)
      3. Restart rnsd (reticulumhf-rnsd.service on g90test) so it
         picks up the new interface config (~3s transport bounce,
         meshchat auto-restarts via Requires=rnsd)

    Competing audio modems (js8call, wsjtx, fldigi, pavucontrol)
    are pkill'd first because they may hold the ALSA loopback
    subdevs that modem73 needs."""
    run_script("toggle_modem73_audio.sh", args=["on"])
    return redirect(url_for("index"))


@app.route("/stop-modem73-loopback", methods=["POST"])
def stop_modem73_loopback():
    """Disable the Modem73 OFDM modem in Reticulum and stop the
    modem73 loopback process. Mirror of /start-modem73-loopback.

    Frees the ALSA loopback subdevs for js8call/wsjtx/fldigi/freedvtnc2.
    rnsd is restarted so it stops trying to TCP-connect to modem73's
    KISS port."""
    run_script("toggle_modem73_audio.sh", args=["off"])
    return redirect(url_for("index"))


@app.route("/reset-modem73-audio", methods=["POST"])
def reset_modem73_audio():
    """Reset modem73 audio device to default (audio_input=0, audio_output=0).

    Use when modem73 fails to start because the saved audio device index
    no longer matches any available hardware (e.g. operator moved the
    digirig between boxes / swapped USB ports, and the ALSA / PipeWire
    card numbering shifted).

    Writes audio_input=0 + audio_output=0 to ~/.config/modem73/settings
    (atomically), then kills + restarts the modem73 loopback subprocess
    so the new settings take effect. Does NOT touch callsign, port,
    modulation, CSMA, tx_drive, or the Reticulum [[Modem73]] block."""
    run_script("reset_modem73_audio.sh")
    return redirect(url_for("index"))

@app.route("/reset-audio", methods=["POST"])
def reset_audio():
    """Reset the audio device stack. Mirrors what
    /usr/local/bin/start-digital-branch does on the g90 box's
    node-portal: stops the digital-mode services that may be holding
    ALSA handles (meshchatx, reticulumhf-rnsd, freedvtnc2), then
    restarts the noVNC session so the X server cycle clears any
    stale audio clients. The shared launcher's web UI is itself served
    on :80, independent of the noVNC session on :6080, so the
    launcher stays up throughout the reset.

    Sequence is ordered: stop the leaf first (meshchatx), then the
    parents, then re-arm the display. This matches the g90 image's
    start-digital-branch script verbatim.

    Note (2026-09-08): the legacy reticulum-meshchat.service used to
    be stopped here too. It's been retired (MeshChatX subsumes it),
    so the stop call for that service was removed. If a box still
    has the legacy service installed, systemctl stop on it would
    silently succeed (the unit just isn't there), so we don't gate
    on its presence.
    """
    subprocess.Popen(
        ["sudo", "-n", "systemctl", "stop", "meshchatx.service"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    subprocess.Popen(
        ["sudo", "-n", "systemctl", "stop", "reticulumhf-rnsd.service"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    subprocess.Popen(
        ["sudo", "-n", "systemctl", "stop", "freedvtnc2.service"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    subprocess.Popen(
        ["sudo", "-n", "systemctl", "start", "novnc-session.service"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return redirect(url_for("index"))


@app.route("/start-pat-http", methods=["POST"])
def start_pat_http():
    """Start the pat-http systemd service (pat-winlink web UI on :5000).

    The web UI is independent of any radio (piardopc, freedvtnc2) — it
    serves a browser-based Winlink inbox that can be used to draft
    messages, browse the local mailbox, and connect via Telnet to a
    CMS. Once the G90 is plugged in and piardopc is up on :8515, pat
    picks up ARDOP automatically (config: ardop.addr = localhost:8515).
    """
    systemctl("restart", "pat-http.service")
    return redirect(url_for("index"))


@app.route("/stop-pat-http", methods=["POST"])
def stop_pat_http():
    """Stop the pat-http systemd service."""
    systemctl("stop", "pat-http.service")
    return redirect(url_for("index"))


@app.route("/reboot-pi", methods=["POST"])
def reboot_pi():
    """Reboot the g90 box. This disconnects SSH, VNC, the launcher,
    node-portal, and any active QSOs / Reticulum sessions. The
    launcher page has a JS confirm() to prevent accidental clicks."""
    subprocess.Popen(
        ["sudo", "-n", "systemctl", "reboot"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return ("<h1>Rebooting...</h1>"
            "<p>The g90 box is rebooting. This page will go down in a few seconds. "
            "Give it ~60s before reconnecting.</p>")


@app.route("/shutdown-pi", methods=["POST"])
def shutdown_pi():
    """Power off the g90 box. This disconnects everything. The
    launcher has a JS confirm() to prevent accidental clicks."""
    subprocess.Popen(
        ["sudo", "-n", "shutdown", "-h", "now"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return ("<h1>Shutting down...</h1>"
            "<p>The g90 box is powering off. You'll need to "
            "physically power it back on to reconnect.</p>")


@app.route("/launcher-update", methods=["POST"])
def update_from_server():
    """POST handler: apply the launcher update and render the result.

    Source of truth: github.com/smeshT/reticulumpi.git (public, HTTPS).
    g90digi pulls from there. m5boss is out of the loop.

    Split from /launcher-status so the POST URL is distinct from the
    GET URL. Browsers sometimes re-POST a URL when you navigate back
    to it; keeping the POST URL separate from the GET-only status
    URL means accidental POSTs (via back button, refresh, etc.) can't
    trigger an update.

    Self-bootstrapping: if /home/pi/shared_launcher/ is not a git
    working tree (e.g. the image baked it in directly, or it was
    renamed out of the way), the first POST clones the repo from
    github into that path. The image-baked `templates/` directory
    is restored from the sibling `shared_launcher.imagebak-*`
    snapshot if present, so the launcher keeps the page-specific
    paths/colors the bare repo doesn't track.

    Failure modes:
    - github unreachable: page says 'unable to check' and falls
      back to 'reflash or scp from m5boss'. No state change.
    - Local divergence: --ff-only refuses; page surfaces the
      error. Launcher stays on the current code.
    - Restart fails: service goes down. User has to ssh in and
      `sudo systemctl start g90-shared-launcher.service` manually.
    """
    import subprocess
    import json
    import shutil

    repo_url = "https://github.com/smeshT/reticulumpi.git"
    manifest_url = "https://raw.githubusercontent.com/smeshT/reticulumpi/main/releases/launcher/latest.json"
    tag_pattern = "refs/tags/v*"

    # --- 1. What's on the box right now? -----------------------------------

    def run_or_default(cmd, default=""):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return r.stdout.strip() if r.returncode == 0 else default
        except Exception:
            return default

    is_worktree = os.path.isdir(os.path.join(LAUNCHER_DIR, ".git"))

    if not os.path.isdir(LAUNCHER_DIR):
        local_version = "missing"
    elif is_worktree:
        local_version = run_or_default(
            ["git", "-C", LAUNCHER_DIR, "describe", "--tags", "--abbrev=0"]
        ) or "untagged"
    else:
        local_version = "image-baked"

    # --- 2. What's the latest tag on github? --------------------------------
    # Probe github with urllib first (avoids git's DNS resolution issues on
    # some networks). If we can fetch latest.json, we know the latest tag.
    #
    # Use the github Contents API instead of raw.githubusercontent.com
    # for latest.json specifically: raw CDN caches stale content for ~5
    # minutes after a push, which means a fresh release isn't visible
    # immediately. The API is uncached for this use case.
    import urllib.request, base64
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/smeshT/reticulumpi/contents/releases/launcher/latest.json",
            headers={"Accept": "application/vnd.github+json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            api = json.loads(resp.read().decode())
        idx = json.loads(base64.b64decode(api["content"]).decode())
        latest_tag = idx.get("latest", "").replace("^{}", "")
        github_reachable = bool(latest_tag)
        manifest_fetch_error = None
    except Exception as e:
        latest_tag = None
        github_reachable = False
        manifest_fetch_error = f"github probe failed: {type(e).__name__}: {e}"

    # --- 3. POST: apply the update -----------------------------------------

    if request.method == "POST":
        log_lines = []

        # Bootstrap: if LAUNCHER_DIR isn't a working tree, clone from github.
        if not is_worktree:
            log_lines.append(f"LAUNCHER_DIR is not a git working tree ({local_version}); bootstrapping from github")
            clone = subprocess.run(
                ["git", "clone", "--depth=50", repo_url, LAUNCHER_DIR],
                capture_output=True, text=True, timeout=120
            )
            if clone.returncode != 0:
                return _render_update_failed(
                    "Bootstrap clone failed",
                    clone.stdout + clone.stderr
                )
            log_lines.append("Cloned from github OK")

            # Restore image-baked templates if a snapshot exists.
            import glob
            snapshots = sorted(glob.glob("/home/pi/shared_launcher.imagebak-*"))
            if snapshots:
                latest_snap = snapshots[-1]
                tpl_src = os.path.join(latest_snap, "templates")
                tpl_dst = os.path.join(LAUNCHER_DIR, "templates")
                if os.path.isdir(tpl_src):
                    shutil.copytree(tpl_src, tpl_dst, dirs_exist_ok=True)
                    log_lines.append(f"Restored image-baked templates from {latest_snap}")
                log_lines.append(f"NOTE: image-baked services (systemd units, pip packages) are NOT auto-installed. Reflash to bring the box in line with {latest_tag or 'the latest image'}.")

            is_worktree = True

        # Fetch + checkout the latest tag.
        if latest_tag and github_reachable:
            fetch = subprocess.run(
                # --force is required because we force-update tags on github
                # during fix-up releases (e.g. v0.6 -> v0.6.1 -> v0.6.2 ->
                # v0.6.3 all point at the same launcher code; we tag
                # the same commit under a new name when shipping a
                # manifest-only fix). Without --force, the fetch refuses
                # to overwrite local tags and the update fails.
                ["git", "-C", LAUNCHER_DIR, "fetch", "--tags", "--force",
                 "--depth=50", "origin"],
                capture_output=True, text=True, timeout=60
            )
            if fetch.returncode != 0:
                return _render_update_failed("git fetch failed", fetch.stdout + fetch.stderr)
            log_lines.append("git fetch OK")

            checkout = subprocess.run(
                # -f overwrites any locally-modified files. The operator
                # clicked "Update", so they explicitly want to clobber
                # local state. (Local mods on the box right now are
                # live-patches we shipped via scp; they'll be replaced
                # by the canonical tag content, which is the same
                # patches + any future fixes.)
                # 2026-09-08: dropped the trailing "-- ." so HEAD moves
                # to the new tag. Without this, the version page's
                # git describe reports the old tag even though files
                # are current (discovered during g90digi v0.6.10
                # deploy). Safe here because deployed boxes don't have
                # local commits to preserve.
                ["git", "-C", LAUNCHER_DIR, "checkout", "-f", latest_tag],
                capture_output=True, text=True, timeout=30
            )
            if checkout.returncode != 0:
                return _render_update_failed(
                    f"git checkout {latest_tag} failed",
                    checkout.stdout + checkout.stderr
                )
            log_lines.append(f"git checkout {latest_tag} OK")

        # Restart the service.
        subprocess.Popen(
            ["sudo", "-n", "systemctl", "restart", LAUNCHER_SERVICE],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        log_lines.append("systemctl restart issued; service will be back in ~3s")

        return (
            "<h1>Updated</h1>"
            "<p>Refresh your browser to load the new launcher.</p>"
            "<h2>log</h2>"
            "<pre style='background:#1a1a1a;color:#ddd;padding:1em;'>"
            + "\n".join(log_lines) +
            "</pre>"
            # Anchor (not form button) so navigating is a fresh GET
            # to a DIFFERENT URL — no browser form-resubmit confusion.
            "<p style='margin-top:1.5em;'>"
            "<a href='/launcher-status' "
            "style='display:inline-block;padding:0.6em 1.2em;"
            "background:#0a6;border:none;border-radius:4px;"
            "color:#fff;text-decoration:none;font-weight:600;'>"
            "Check Components</a>"
            "</p>"
            "<p style='color:#888;font-size:0.9em;'>"
            "Click here to check the system for missing and outdated "
            "components (no update applied)."
            "</p>"
            "<p><a href='/'>Back to launcher</a></p>"
        )

    # --- 4. GET: render the version page ------------------------------------

    # Pull the manifest for the component check.
    # manifest_fetch_error was already set by the github probe above; we
    # only need to actually fetch and parse the manifest here.
    #
    # Use the github Contents API to dodge the raw.githubusercontent.com
    # CDN cache (~5min TTL on raw content after a push). The API call
    # below returns base64 in 'content' which we decode.
    import base64
    def _fetch_manifest_json(url):
        # Translate raw.githubusercontent.com URLs to the github API,
        # so a fresh push is visible immediately on the next click.
        # Format: https://raw.githubusercontent.com/<owner>/<repo>/<ref>/<path>
        # API:     https://api.github.com/repos/<owner>/<repo>/contents/<path>?ref=<ref>
        if url.startswith("https://raw.githubusercontent.com/"):
            stripped = url[len("https://raw.githubusercontent.com/"):]
            parts = stripped.split("/", 3)
            if len(parts) == 4:
                owner, repo, ref, path = parts
                api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref}"
                req = urllib.request.Request(
                    api_url,
                    headers={"Accept": "application/vnd.github+json"}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    api = json.loads(resp.read().decode())
                return json.loads(base64.b64decode(api["content"]).decode())
        # Fallback: fetch as raw JSON (works for non-github URLs and the
        # API fallback).
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode())

    manifest = None
    if github_reachable:
        try:
            idx = _fetch_manifest_json(manifest_url)
            manifest_url_full = idx.get("manifest_url")
            if manifest_url_full:
                manifest = _fetch_manifest_json(manifest_url_full)
            else:
                manifest_fetch_error = "latest.json missing manifest_url field"
        except Exception as e:
            manifest_fetch_error = f"{type(e).__name__}: {e}"

    # Run the box-status collector (if it's shipped with this version).
    box_status = None
    collector = os.path.join(LAUNCHER_DIR, "scripts", "collect-box-status.sh")
    if os.path.isfile(collector):
        try:
            cs = subprocess.run(
                ["bash", collector],
                capture_output=True, text=True, timeout=10,
                env={**os.environ, "LAUNCHER_DIR": LAUNCHER_DIR}
            )
            if cs.returncode == 0 and cs.stdout.strip():
                box_status = json.loads(cs.stdout)
        except Exception:
            box_status = None

    # Diff manifest vs box-state for the component check.
    component_rows = []
    if manifest and box_status:
        # systemd units
        # Manifest names include the ".service" suffix; collector strips
        # it. Strip it from manifest keys when looking up.
        manifest_units = {u["name"]: u for u in manifest["components"].get("systemd_units", [])}
        actual_units = {u["name"]: u["state"] for u in box_status.get("systemd_units", [])}
        for unit_name, _ in manifest_units.items():
            lookup = unit_name.removesuffix(".service")
            state = actual_units.get(lookup, "missing")
            ok = state == "active"
            mark = "✓" if ok else "✗"
            component_rows.append((ok, f"{mark} {unit_name:<28} {state}"))

        # pip packages
        manifest_pkgs = manifest["components"].get("pip_packages", [])
        actual_pkgs_by_venv = {
            p["venv"]: dict(
                (seg.split("==")[0], seg.split("==")[1])
                for seg in p["packages"].split(",") if "==" in seg
            )
            for p in box_status.get("pip_packages", [])
        }
        for spec in manifest_pkgs:
            venv = spec["venv"]
            pkg = spec["package"]
            min_v = spec.get("min_version", "")
            installed = actual_pkgs_by_venv.get(venv, {}).get(pkg)
            if installed is None:
                ok = False
                detail = "not installed"
            else:
                # Lexical compare is fine for semver tags; ship a real
                # version compare if we ever care about 1.10 > 1.9.
                ok = installed >= min_v
                detail = f"{installed}" + (f" (need >= {min_v})" if not ok else "")
            mark = "✓" if ok else "✗"
            component_rows.append((ok, f"{mark} {pkg} ({venv})" + (f"  {detail}" if detail else "")))

        # config files
        for spec in manifest["components"].get("config_files", []):
            path = spec["path"]
            wanted_mode = spec.get("mode")
            actual = next(
                (f for f in box_status.get("config_files", []) if f["path"] == path),
                None
            )
            if actual is None or not actual.get("exists"):
                ok = False
                detail = "missing"
            elif wanted_mode:
                # Normalize both modes to a 4-digit zero-padded octal string
                # so "0755" and "755" compare equal.
                want_norm = str(wanted_mode).zfill(4)
                got_norm = str(actual.get("mode", "")).zfill(4)
                if got_norm != want_norm:
                    ok = False
                    detail = f"mode {got_norm} (want {want_norm})"
                else:
                    ok = True
                    detail = "present"
            else:
                ok = True
                detail = "present"
            mark = "✓" if ok else "✗"
            component_rows.append((ok, f"{mark} {path}  {detail}"))

    # Compose the page.
    rows_html = "\n".join(
        f"<li>{row}</li>" for _, row in component_rows
    ) if component_rows else (
        "<li>(component check unavailable — "
        + (manifest_fetch_error or "manifest not loaded")
        + ")</li>"
    )

    if not github_reachable:
        latest_line = "<p><strong>Latest:</strong> (github unreachable)</p>"
        update_button = "<p><em>Updates unavailable. Reflash the image, or scp from m5boss.</em></p>"
    elif local_version == "missing":
        latest_line = f"<p><strong>Latest:</strong> {latest_tag}</p>"
        update_button = (
            "<form method='POST'>"
            "<button type='submit' onclick=\"return confirm('Bootstrap launcher from github?');\">"
            f"Bootstrap launcher ({latest_tag})"
            "</button></form>"
        )
    elif local_version == "image-baked":
        latest_line = f"<p><strong>Latest:</strong> {latest_tag}</p>"
        update_button = (
            "<form method='POST'>"
            "<button type='submit' onclick=\"return confirm('Bootstrap launcher from github?');\">"
            f"Bootstrap launcher ({latest_tag})"
            "</button></form>"
        )
    elif local_version == latest_tag:
        latest_line = f"<p><strong>Latest:</strong> {latest_tag} (you're up to date)</p>"
        update_button = "<p><em>Up to date.</em></p>"
    else:
        latest_line = f"<p><strong>Latest:</strong> {latest_tag}</p>"
        update_button = (
            "<form method='POST'>"
            "<button type='submit' onclick=\"return confirm('Update and restart?');\">"
            f"Update launcher to {latest_tag}"
            "</button></form>"
        )

    missing_count = sum(1 for ok, _ in component_rows if not ok)

    if component_rows and missing_count == 0:
        summary = f"<p><strong>All components match {latest_tag}.</strong></p>"
    elif component_rows and missing_count > 0:
        summary = (
            f"<p><strong>{missing_count} component(s) missing or out of date.</strong> "
            "Reflash the image, or install manually.</p>"
        )
    else:
        summary = ""

    return (
        "<h1>Launcher update</h1>"
        f"<p><strong>Your version:</strong> {local_version}</p>"
        + latest_line
        + update_button
        + "<h2>Component check</h2>"
        + "<ul style='font-family:monospace;'>"
        + rows_html
        + "</ul>"
        + summary
        + "<p style='margin-top:2em;'><a href='/'>Back to launcher</a></p>"
    )


def _render_update_failed(title, body):
    """Helper for the update-failed page. Same shape as the old
    version-page failure block."""
    return (
        "<h1>Update failed</h1>"
        f"<p>{title}. The launcher is still running on the previous code.</p>"
        "<h2>log</h2>"
        "<pre style='background:#1a1a1a;color:#ddd;padding:1em;'>"
        + body.replace("<", "&lt;") +
        "</pre>"
        "<p style='margin-top:1.5em;'>"
        "<a href='/launcher-status' "
        "style='display:inline-block;padding:0.6em 1.2em;"
        "background:#0a6;border:none;border-radius:4px;"
        "color:#fff;text-decoration:none;font-weight:600;'>"
        "Check Components</a>"
        "</p>"
        "<p style='color:#888;font-size:0.9em;'>"
        "Click here to check the system for missing and outdated "
        "components (no update applied)."
        "</p>"
        "<p><a href='/'>Back to launcher</a></p>"
    )


@app.route("/launcher-status", methods=["GET"])
def launcher_status():
    """GET-only handler: render the version page (your version,
    latest, component check). Read-only — no update applied.

    Split from /launcher-update so the GET URL is distinct from
    the POST URL. The Update button on the launcher home page
    POSTs to /launcher-update; this route is the destination of
    the 'Check Components' button on the update result page.

    Refreshing this page (F5 / Ctrl+R) is safe; it's idempotent.
    """
    return _render_status_page()


def _render_status_page():
    """Render the version page (your version, latest, component check).

    Read-only. Pulls from github (latest tag + manifest) and the
    local collector script. No state change.
    """
    import json
    import base64
    import urllib.request
    import subprocess

    repo_url = "https://github.com/smeshT/reticulumpi.git"
    manifest_url = "https://raw.githubusercontent.com/smeshT/reticulumpi/main/releases/launcher/latest.json"

    def run_or_default(cmd, default=""):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return r.stdout.strip() if r.returncode == 0 else default
        except Exception:
            return default

    is_worktree = os.path.isdir(os.path.join(LAUNCHER_DIR, ".git"))

    if not os.path.isdir(LAUNCHER_DIR):
        local_version = "missing"
    elif is_worktree:
        local_version = (
            run_or_default(
                ["git", "-C", LAUNCHER_DIR, "describe", "--tags", "--abbrev=0"]
            ).replace("^{}", "")
        ) or "untagged"
    else:
        local_version = "image-baked"

    # Probe github via the Contents API to dodge raw.githubusercontent.com
    # CDN caching (~5min TTL on raw content after a push).
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/smeshT/reticulumpi/contents/releases/launcher/latest.json",
            headers={"Accept": "application/vnd.github+json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            api = json.loads(resp.read().decode())
        idx = json.loads(base64.b64decode(api["content"]).decode())
        latest_tag = idx.get("latest", "").replace("^{}", "")
        github_reachable = bool(latest_tag)
        manifest_fetch_error = None
    except Exception as e:
        latest_tag = None
        github_reachable = False
        manifest_fetch_error = f"github probe failed: {type(e).__name__}: {e}"

    manifest = None
    if github_reachable:
        try:
            def _fetch_manifest_json(url):
                # Translate raw.githubusercontent.com URLs to the github
                # Contents API to bypass the raw CDN cache.
                if url.startswith("https://raw.githubusercontent.com/"):
                    stripped = url[len("https://raw.githubusercontent.com/"):]
                    parts = stripped.split("/", 3)
                    if len(parts) == 4:
                        owner, repo, ref, path = parts
                        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref}"
                        req = urllib.request.Request(
                            api_url,
                            headers={"Accept": "application/vnd.github+json"}
                        )
                        with urllib.request.urlopen(req, timeout=5) as resp:
                            api = json.loads(resp.read().decode())
                        return json.loads(base64.b64decode(api["content"]).decode())
                with urllib.request.urlopen(url, timeout=5) as resp:
                    return json.loads(resp.read().decode())

            idx = _fetch_manifest_json(manifest_url)
            manifest_url_full = idx.get("manifest_url")
            if manifest_url_full:
                manifest = _fetch_manifest_json(manifest_url_full)
            else:
                manifest_fetch_error = "latest.json missing manifest_url field"
        except Exception as e:
            manifest_fetch_error = f"{type(e).__name__}: {e}"

    # Run the box-status collector (if it's shipped with this version).
    box_status = None
    collector = os.path.join(LAUNCHER_DIR, "scripts", "collect-box-status.sh")
    if os.path.isfile(collector):
        try:
            cs = subprocess.run(
                ["bash", collector],
                capture_output=True, text=True, timeout=10,
                env={**os.environ, "LAUNCHER_DIR": LAUNCHER_DIR}
            )
            if cs.returncode == 0 and cs.stdout.strip():
                box_status = json.loads(cs.stdout)
        except Exception:
            box_status = None

    # Diff manifest vs box-state for the component check.
    component_rows = []
    if manifest and box_status:
        # systemd units
        manifest_units = {u["name"]: u for u in manifest["components"].get("systemd_units", [])}
        actual_units = {u["name"]: u["state"] for u in box_status.get("systemd_units", [])}
        for unit_name, _ in manifest_units.items():
            lookup = unit_name.removesuffix(".service")
            state = actual_units.get(lookup, "missing")
            ok = state == "active"
            mark = "✓" if ok else "✗"
            component_rows.append((ok, f"{mark} {unit_name:<28} {state}"))

        # pip packages
        manifest_pkgs = manifest["components"].get("pip_packages", [])
        actual_pkgs_by_venv = {
            p["venv"]: dict(
                (seg.split("==")[0], seg.split("==")[1])
                for seg in p["packages"].split(",") if "==" in seg
            )
            for p in box_status.get("pip_packages", [])
        }
        for spec in manifest_pkgs:
            venv = spec["venv"]
            pkg = spec["package"]
            min_v = spec.get("min_version", "")
            installed = actual_pkgs_by_venv.get(venv, {}).get(pkg)
            if installed is None:
                ok = False
                detail = "not installed"
            else:
                ok = installed >= min_v
                detail = f"{installed}" + (f" (need >= {min_v})" if not ok else "")
            mark = "✓" if ok else "✗"
            component_rows.append((ok, f"{mark} {pkg} ({venv})" + (f"  {detail}" if detail else "")))

        # config files
        for spec in manifest["components"].get("config_files", []):
            path = spec["path"]
            wanted_mode = spec.get("mode")
            actual = next(
                (f for f in box_status.get("config_files", []) if f["path"] == path),
                None
            )
            if actual is None or not actual.get("exists"):
                ok = False
                detail = "missing"
            elif wanted_mode:
                want_norm = str(wanted_mode).zfill(4)
                got_norm = str(actual.get("mode", "")).zfill(4)
                if got_norm != want_norm:
                    ok = False
                    detail = f"mode {got_norm} (want {want_norm})"
                else:
                    ok = True
                    detail = "present"
            else:
                ok = True
                detail = "present"
            mark = "✓" if ok else "✗"
            component_rows.append((ok, f"{mark} {path}  {detail}"))

    # Compose the page.
    rows_html = "\n".join(
        f"<li>{row}</li>" for _, row in component_rows
    ) if component_rows else (
        "<li>(component check unavailable — "
        + (manifest_fetch_error or "manifest not loaded")
        + ")</li>"
    )

    if not github_reachable:
        latest_line = "<p><strong>Latest:</strong> (github unreachable)</p>"
        update_button = (
            "<form method='POST' action='/launcher-update'>"
            "<button type='submit' disabled>Update launcher</button>"
            "</form>"
            "<p><em>Updates unavailable. Reflash the image, or scp from m5boss.</em></p>"
        )
    elif local_version == "missing":
        latest_line = f"<p><strong>Latest:</strong> {latest_tag}</p>"
        update_button = (
            "<form method='POST' action='/launcher-update'>"
            "<button type='submit' onclick=\"return confirm('Bootstrap launcher from github?');\">"
            f"Bootstrap launcher ({latest_tag})"
            "</button></form>"
        )
    elif local_version == "image-baked":
        latest_line = f"<p><strong>Latest:</strong> {latest_tag}</p>"
        update_button = (
            "<form method='POST' action='/launcher-update'>"
            "<button type='submit' onclick=\"return confirm('Bootstrap launcher from github?');\">"
            f"Bootstrap launcher ({latest_tag})"
            "</button></form>"
        )
    elif local_version == latest_tag:
        latest_line = f"<p><strong>Latest:</strong> {latest_tag} (you're up to date)</p>"
        update_button = "<p><em>Up to date.</em></p>"
    else:
        latest_line = f"<p><strong>Latest:</strong> {latest_tag}</p>"
        update_button = (
            "<form method='POST' action='/launcher-update'>"
            "<button type='submit' onclick=\"return confirm('Update and restart?');\">"
            f"Update launcher to {latest_tag}"
            "</button></form>"
        )

    missing_count = sum(1 for ok, _ in component_rows if not ok)

    if component_rows and missing_count == 0:
        summary = f"<p><strong>All components match {latest_tag}.</strong></p>"
    elif component_rows and missing_count > 0:
        summary = (
            f"<p><strong>{missing_count} component(s) missing or out of date.</strong> "
            "Reflash the image, or install manually.</p>"
        )
    else:
        summary = ""

    return (
        "<h1>Launcher update</h1>"
        f"<p><strong>Your version:</strong> {local_version}</p>"
        + latest_line
        + update_button
        + "<h2>Component check</h2>"
        + "<ul style='font-family:monospace;'>"
        + rows_html
        + "</ul>"
        + summary
        + "<p style='margin-top:2em;'><a href='/'>Back to launcher</a></p>"
    )


# Backwards-compat alias: /update-from-server redirects GET to
# /launcher-status and forwards POST to the same handler as
# /launcher-update. This keeps the upgrade path safe during the
# URL rename — old bookmarks, the form action on the launcher home
# page (until the template is updated), and any external links
# continue to work.
from flask import redirect  # noqa: E402
@app.route("/update-from-server", methods=["GET"])
def update_from_server_legacy_get():
    return redirect("/launcher-status", code=302)

@app.route("/update-from-server", methods=["POST"])
def update_from_server_legacy_post():
    # Forward to the canonical POST handler.
    return update_from_server()


# ---------------------------------------------------------------------------
# Config backup / restore
# ---------------------------------------------------------------------------
#
# Pattern source: sbitx's toolbox app. Operator-facing flow is
# two pages:
#
#   GET  /backup-configs   -> download a fresh .tar.gz of the
#                              live box's whitelisted config
#                              files (Reticulum, modem73, js8call,
#                              fldigi, flrig, wsjtx, pat, hostapd,
#                              etc.) -> rotates to last 5 in
#                              /home/pi/shared_launcher/backups/
#   GET  /restore-configs  -> upload form + a list of the last
#                              5 in-box archives (so the operator
#                              can restore from one without
#                              needing to download + re-upload)
#   POST /restore-configs/preview
#                           -> extract to a staging dir, compute
#                              a diff against the live files,
#                              return an HTML page listing every
#                              file with action: add / replace /
#                              skip, plus a confirm button
#   POST /restore-configs/apply/<token>
#                           -> copy staged files to live paths,
#                              wipe the staging dir, restart
#                              affected services, return a
#                              summary page
#   POST /restore-configs/cancel/<token>
#                           -> wipe the staging dir, return
#                              to the upload form
#
# Box-specific backup (per operator 2026-09-09 21:38 MDT):
# restoring a backup from box A to box B gives box B box A's
# Reticulum identity. That's usually what you want (so the
# rest of the fleet can find the new box) but is documented
# on the restore page.

@app.route("/backup-configs", methods=["GET"])
def backup_configs():
    """Build a tar.gz of the live box's whitelisted config
    files and return it as a download. Also keeps a copy in
    /home/pi/shared_launcher/backups/ (rotated to last 5)."""
    try:
        tar_bytes, manifest = config_backup.build_backup_tarball()
    except Exception as e:
        return f"<h1>Backup failed</h1><p>{e}</p>", 500

    # Persist a copy on the box (rotated).
    config_backup.save_backup_and_rotate(tar_bytes, manifest)

    # Stream it back to the operator.
    return send_file(
        io_for_send(tar_bytes),
        mimetype="application/gzip",
        as_attachment=True,
        download_name=config_backup.backup_filename(manifest),
    )


@app.route("/restore-configs", methods=["GET"])
def restore_configs_form():
    """Upload form. Also lists the last 5 in-box archives so
    the operator can restore from a recent backup without
    having to re-download it."""
    backups = config_backup.list_backups()
    rows = "".join(
        f"<li><form method='POST' action='/restore-configs/from-archive' "
        f"style='display:inline'>"
        f"<input type='hidden' name='filename' value='{b['filename']}'>"
        f"<button>Restore</button></form> "
        f"<code>{b['filename']}</code> "
        f"<span style='color:#666'>({b['size']:,} bytes, "
        f"{b['mtime']})</span></li>"
        for b in backups
    )
    if not rows:
        rows = ("<li><em>No on-box backups yet. Use the form below "
                "to upload one.</em></li>")
    return (
        "<h1>Restore configs</h1>"
        "<p>Upload a <code>g90-configs-*.tar.gz</code> archive to "
        "see what would change. Restoring is a two-step process: "
        "first you'll see a preview, then confirm to apply.</p>"
        "<p><b>Heads up:</b> backups include the box's Reticulum "
        "node identity. Restoring a backup from a different box "
        "gives this box the old box's identity on the mesh.</p>"
        "<h2>Upload a backup</h2>"
        "<form method='POST' enctype='multipart/form-data' "
        "action='/restore-configs/preview'>"
        "<input type='file' name='archive' accept='.tar.gz,.tgz' "
        "required>"
        "<button>Preview</button></form>"
        "<h2>Or restore from a recent on-box backup</h2>"
        f"<ul>{rows}</ul>"
        "<p style='margin-top:2em;'><a href='/'>Back to launcher</a></p>"
    )


@app.route("/restore-configs/preview", methods=["POST"])
def restore_configs_preview():
    """Extract the upload to a staging dir, compute a diff
    against the live files, render the preview page."""
    # Two ways to get here: the upload form, or the
    # from-archive form. The from-archive form posts a
    # `filename` field; the upload form posts the file
    # as `archive`.
    if "filename" in request.form:
        # Restore from an in-box archive.
        fname = request.form["filename"]
        fpath = os.path.join(config_backup.BACKUP_DIR, fname)
        if not os.path.isfile(fpath):
            return (f"<h1>Archive not found</h1>"
                    f"<p><code>{fname}</code> is not in "
                    f"<code>{config_backup.BACKUP_DIR}</code>.</p>"
                    f"<p><a href='/restore-configs'>Back</a></p>"), 404
        with open(fpath, "rb") as f:
            tar_bytes = f.read()
    else:
        # Upload form. request.files['archive'] is a
        # FileStorage; .read() gives bytes.
        upload = request.files.get("archive")
        if not upload or not upload.filename:
            return ("<h1>No file uploaded</h1>"
                    "<p><a href='/restore-configs'>Back</a></p>"), 400
        tar_bytes = upload.read()

    try:
        token, staging, members = (
            config_backup.extract_to_staging(tar_bytes)
        )
    except ValueError as e:
        return (f"<h1>Could not read archive</h1><p>{e}</p>"
                f"<p><a href='/restore-configs'>Back</a></p>"), 400

    diff = config_backup.compute_diff(staging)
    # Persist a tiny session file mapping token -> staging
    # dir. The token is in the URL so we don't need cookies.
    # (The staging dir already lives at RESTORE_STAGING/<token>
    # — that's the mapping; we just need the token round-trip
    # to be in the URL the operator clicks.)
    rows = []
    for item in diff["items"]:
        cls = {"add": "ok", "replace": "warn", "skip": "dim"}[
            item["action"]]
        rows.append(
            f"<tr class='{cls}'>"
            f"<td>{item['action']}</td>"
            f"<td><code>{item['path']}</code></td>"
            f"<td style='text-align:right'>{item['size']:,}</td>"
            f"</tr>"
        )
    table = "".join(rows) or (
        "<tr><td colspan='3'><em>No files in archive</em></td></tr>"
    )
    summary = (
        f"<p><b>{sum(1 for x in diff['items'] if x['action'] == 'add')}"
        f" added</b>, "
        f"<b>{sum(1 for x in diff['items'] if x['action'] == 'replace')}"
        f" replaced</b>, "
        f"{sum(1 for x in diff['items'] if x['action'] == 'skip')}"
        f" unchanged.</p>"
    )
    apply_button = (
        f"<form method='POST' "
        f"action='/restore-configs/apply/{token}' "
        f"onsubmit=\"return confirm('Apply {sum(1 for x in diff['items'] if x['action'] in ('add','replace'))} file changes and restart affected services? The launcher will be down for ~5s during the restart.');\">"
        f"<button class='warn'>Apply</button></form>"
        if diff["action_required"] else
        "<p><em>No changes needed — archive is already in sync "
        "with the live box.</em></p>"
    )
    return (
        f"<h1>Restore preview</h1>"
        f"<p>Token: <code>{token}</code> (valid until you click "
        f"Apply or Cancel).</p>"
        f"{summary}"
        f"<table border='1' cellpadding='4' style='border-collapse:"
        f"collapse; font-family:monospace;'>"
        f"<tr><th>action</th><th>path</th><th>size</th></tr>"
        f"{table}</table>"
        f"<p style='margin-top:1em;'>{apply_button}"
        f"<form method='POST' action='/restore-configs/cancel/{token}' "
        f"style='display:inline'>"
        f"<button>Cancel</button></form></p>"
        f"<p style='margin-top:2em;'><a href='/'>Back to launcher</a></p>"
    )


@app.route("/restore-configs/apply/<token>", methods=["POST"])
def restore_configs_apply(token):
    """Copy staged files to live paths, wipe the staging
    dir, restart affected services."""
    staging = os.path.join(config_backup.RESTORE_STAGING, token)
    if not os.path.isdir(staging):
        return ("<h1>Token expired</h1>"
                "<p>The staging dir for that token no longer "
                "exists. Please re-upload.</p>"
                "<p><a href='/restore-configs'>Back</a></p>"), 410
    try:
        written = config_backup.apply_staging(staging)
    except Exception as e:
        return (f"<h1>Apply failed</h1><p>{e}</p>"
                f"<p><a href='/restore-configs'>Back</a></p>"), 500
    # Staging is consumed; wipe it.
    config_backup.discard_staging(token)
    # Restart services so they pick up new config. The
    # launcher itself is in the list — it'll be down for
    # ~3s, then come back at the same URL.
    config_backup.restart_services_after_restore()
    rows = "".join(f"<li><code>{p}</code></li>" for p in written)
    return (
        f"<h1>Restore applied</h1>"
        f"<p>Wrote {len(written)} files. Services restarting now; "
        f"the launcher itself is in the list so you'll see this "
        f"page's redirect interrupted — refresh in ~5s.</p>"
        f"<ul>{rows}</ul>"
        f"<p style='margin-top:2em;'><a href='/'>Back to launcher</a></p>"
    )


@app.route("/restore-configs/cancel/<token>", methods=["POST"])
def restore_configs_cancel(token):
    """Wipe the staging dir, return to the upload form."""
    config_backup.discard_staging(token)
    return redirect("/restore-configs", code=302)


@app.route("/restore-configs/from-archive", methods=["POST"])
def restore_configs_from_archive():
    """Helper: redirect the from-archive POST into the
    preview handler with the same payload."""
    # The restore_configs_preview handler reads `filename`
    # from request.form; the form posts to here. We just
    # forward by re-invoking the preview handler with
    # the same request context — Flask supports this
    # via a direct call.
    return restore_configs_preview()


# send_file wants a file-like object, but we have bytes in
# memory. This wraps bytes as a BytesIO that send_file will
# read once. Cheaper than hitting disk for a 50-200 KB
# tarball. We avoid module-level `import io` collision by
# importing it here (config_backup already imports it).
import io as _io
def io_for_send(b):
    return _io.BytesIO(b)


if __name__ == "__main__":
    # Listen on 0.0.0.0:80 (the g90's entry-point port). The
    # shared launcher is the captive-portal homepage on the g90
    # (per @Mmsp907 2026-08-09); node-portal is on :8081 and
    # reticulumhf-portal on :8080. The 2026-07-19 port-80 incident
    # (commit a461f3b) is the historical reason we are careful
    # here: the launcher unit MUST set Environment=LAUNCHER_PORT=80
    # for Linux to allow binding :80 from User=pi without root
    # (setcap cap_net_bind_service=+ep /usr/bin/python3.11).
    #
    # If a future commit wants the launcher on a different port,
    # update BOTH the g90-shared-launcher.service unit (with
    # Environment=LAUNCHER_PORT=) AND this default. Keep them in sync.
    port = int(os.environ.get("LAUNCHER_PORT", "80"))
    app.run(host="0.0.0.0", port=port)
