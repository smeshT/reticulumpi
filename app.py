from flask import Flask, render_template, redirect, url_for, request
import subprocess
import os
import re

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


def service_active(name):
    return subprocess.run(
        ["systemctl", "is-active", "--quiet", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    ).returncode == 0


def run_script(name):
    subprocess.Popen(
        [f"{SCRIPTS}/{name}"],
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
    tag is set on the bare repo at /home/pi/repos/g90-launcher.git
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
    # dict order is reading order. Grouped to match the launcher's
    # panel sections: digimodes (FLrig / JS8Call / FLDigi / WSJT-X),
    # then Pavucontrol (also a quick-launch), then the Pat pair
    # (Pat Menu + its web UI), then the Reticulum stack
    # (RNS / MeshChat / FreeDV TNC).
    #
    # FreeDV TNC is green if EITHER freedvtnc2.service is active (the
    # --no-cli daemon that meshchat uses as its KISS modem) OR an
    # lxterminal running the freedvtnc2 CLI is open (the user's
    # interactive TUI in noVNC). Both bind the audio device and both
    # make the modem "up" from the user's perspective; the distinction
    # is which mode (headless vs interactive) is in use, not whether
    # the modem works.
    status = {
        "FLrig": is_running("flrig"),
        "JS8Call": is_running("js8call"),
        "FLDigi": is_running("fldigi"),
        "WSJT-X": is_running("wsjtx"),
        "Pavucontrol": is_running("pavucontrol"),
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
        "RNS": service_active("reticulumhf-rnsd.service"),
        "MeshChat": service_active("reticulum-meshchat.service"),
        "FreeDV TNC": service_active("freedvtnc2.service")
                     or is_running_proc_with_arg("lxterminal", "--title=freedvtnc2"),
        # freeDV Waterfall (diagnostic spectrogram) — green iff an
        # lxterminal with --title=freedv-waterfall is open. The
        # is_running_proc_with_arg helper avoids the pgrep self-match
        # bug: the bare pattern "--title=freedv-waterfall" is in the
        # caller's argv (we set it in start_waterfall.sh), so
        # pgrep -f would match this Python process.
        "Waterfall": is_running_proc_with_arg("lxterminal", "--title=freedv-waterfall"),
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


@app.route("/start-waterfall", methods=["POST"])
def start_waterfall():
    """Open the freeDV Waterfall diagnostic terminal. Mirrors
    start-freedv-tui but does NOT stop freedvtnc2 first: the
    waterfall reads from the "g90audio" dsnoop device (defined
    in /etc/asound.conf), so the TNC and the waterfall can hold
    the G90 audio open simultaneously. That's the whole point
    of having it as a diagnostic — you can see the spectrum
    while the Reticulum stack is up and active, without having
    to tear anything down.

    The audio-device pre-flight lives in start_waterfall.sh
    (same non-fragile UX as freedv_tui.sh: if the G90 isn't
    plugged in, the script opens the terminal with a clear
    "plug in the G90" message instead of letting the Python
    tool fail with an opaque ALSA error)."""
    run_script("start_waterfall.sh")
    return redirect(url_for("index"))


@app.route("/stop-waterfall", methods=["POST"])
def stop_waterfall():
    """Close the freeDV Waterfall lxterminal. Same pattern as
    stop-freedv-tui: kill by --title match so we don't touch
    other lxterminals the user has open on the desktop."""
    subprocess.Popen(
        ["pkill", "-f", "lxterminal.*--title=freedv-waterfall"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
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
    """Close the FreeDV TUI lxterminal. Kills any lxterminal whose
    title is "freedvtnc2" (the script sets --title=freedvtnc2).
    Using pkill on the title pattern is more reliable than pkill
    on the binary name alone, which would also match other
    lxterminals the user has open.
    """
    subprocess.Popen(
        ["pkill", "-f", "lxterminal.*--title=freedvtnc2"],
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


@app.route("/start-reticulum", methods=["POST"])
def start_reticulum():
    """Start the g90 Reticulum stack: rnsd + meshchat + freedvtnc2
    (KISS TNC for the mesh). The g90's services are named
    reticulumhf-rnsd (not the generic rnsd the sbitx box uses) and
    reticulum-meshchat. freedvtnc2.service is the KISS TNC that
    serves the mesh on tcp:8001; it is intentionally NOT enabled
    at boot (it would crashloop without a G90 plugged in). The
    launcher's Reticulum Stack: Start button is the canonical
    trigger for the full Reticulum side of the box.

    We reset-failed first because freedvtnc2 can land in systemd's
    rate-limited "failed" state if it crashloops (e.g. the user
    clicked Start before plugging in the G90, or the radio was
    unplugged mid-QSO). The unit's StartLimitBurst=5 / interval=60s
    means that after 5 fast failures, `systemctl start` is a no-op
    until you `systemctl reset-failed`. Doing the reset here makes
    the Start button idempotent across the boot-without-radio case.
    """
    # Order matters: rnsd first (the daemon the other two depend on),
    # then meshchat (broadcasts announces), then freedvtnc2 (the KISS
    # TNC the mesh uses as a modem). freedvtnc2.service itself has
    # After=network.target rigctld.service and Wants=rigctld.service,
    # so systemd will additionally wait for rigctld before starting
    # the TNC.
    systemctl("reset-failed", "reticulumhf-rnsd.service", "reticulum-meshchat.service", "freedvtnc2.service")
    systemctl("start", "reticulumhf-rnsd.service", "reticulum-meshchat.service", "freedvtnc2.service")
    return redirect(url_for("index"))


@app.route("/stop-reticulum", methods=["POST"])
def stop_reticulum():
    """Stop the g90 Reticulum stack. Order matters: meshchat first
    (so it stops broadcasting announces), then rnsd, then the
    freedvtnc2 KISS TNC. Stopping the TNC last lets the mesh notice
    the KISS endpoint going away before rnsd itself disappears.
    """
    systemctl("stop", "reticulum-meshchat.service")
    systemctl("stop", "reticulumhf-rnsd.service")
    systemctl("stop", "freedvtnc2.service")
    return redirect(url_for("index"))


@app.route("/restart-reticulum", methods=["POST"])
def restart_reticulum():
    """Restart rnsd and meshchat in place. meshchat auto-reconnects
    once rnsd is back."""
    systemctl("restart", "reticulumhf-rnsd.service", "reticulum-meshchat.service")
    return redirect(url_for("index"))


@app.route("/reset-audio", methods=["POST"])
def reset_audio():
    """Reset the audio device stack. Mirrors what
    /usr/local/bin/start-digital-branch does on the g90 box's
    node-portal: stops the digital-mode services that may be holding
    ALSA handles (reticulum-meshchat, reticulumhf-rnsd, freedvtnc2),
    then restarts the noVNC session so the X server cycle clears any
    stale audio clients. The shared launcher's web UI is itself served
    on :8090, independent of the noVNC session on :6080, so the
    launcher stays up throughout the reset.

    Sequence is ordered: stop the leaf first (meshchat), then the
    parents, then re-arm the display. This matches the g90 image's
    start-digital-branch script verbatim.
    """
    subprocess.Popen(
        ["sudo", "-n", "systemctl", "stop", "reticulum-meshchat.service"],
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


@app.route("/update-from-server", methods=["POST"])
def update_from_server():
    """Pull the latest from the central repo at
    pi@nomadpi.local:/home/pi/repos/g90-launcher.git and
    restart the launcher service. The g90 is a clone of
    that repo, so a `git pull --ff-only` brings in any
    new commits the workspace has pushed.

    The button has a JS confirm() so accidental clicks
    don't restart the launcher mid-session. After the
    pull + restart, the page renders a status block
    showing what changed (or "Already up to date").

    Failure modes:
    - Network/SSH down: git pull errors, we surface
      the error in the page. Launcher stays on the
      current code.
    - Local divergence (someone edited on the g90):
      --ff-only rejects the pull, we surface the
      error. Launcher stays on the current code.
    - Restart fails: service goes down. User has to
      SSH in and `sudo systemctl start
      g90-shared-launcher.service` manually.
    """
    import subprocess
    # 1. pull (--ff-only refuses if there are local commits)
    pull = subprocess.run(
        ["git", "-C", LAUNCHER_DIR,
         "pull", "--ff-only", "origin", "master"],
        capture_output=True, text=True, timeout=30,
    )
    if pull.returncode != 0:
        return (
            "<h1>Update failed</h1>"
            "<p>git pull returned non-zero. The launcher is still "
            "running on the previous code. Common causes:</p>"
            "<ul>"
            "<li>Network/SSH to the nomadpi is down</li>"
            "<li>Local edits on this g90 (--ff-only refuses "
            "non-fast-forward pulls)</li>"
            "</ul>"
            "<pre style='background:#1a1a1a;color:#ddd;padding:1em;'>"
            + pull.stdout.replace("<", "&lt;") + "\n"
            + pull.stderr.replace("<", "&lt;") +
            "</pre>"
            "<p><a href='/'>Back to launcher</a></p>"
        )
    # 2. restart the service. The old process exits, the
    # service comes back with the new code. The user's
    # browser will lose the connection mid-load and
    # they'll need to refresh.
    subprocess.Popen(
        ["sudo", "-n", "systemctl", "restart",
         LAUNCHER_SERVICE],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    # Give the service a moment to start, then build the page
    import time
    time.sleep(2)
    return (
        "<h1>Updated</h1>"
        "<p>git pull succeeded and the launcher service was "
        "restarted. <strong>Refresh your browser</strong> to "
        "load the new code.</p>"
        "<h2>git pull output</h2>"
        "<pre style='background:#1a1a1a;color:#ddd;padding:1em;'>"
        + (pull.stdout or "(no output — already up to date)").replace("<", "&lt;") +
        "</pre>"
        "<p><a href='/'>Back to launcher</a></p>"
    )


if __name__ == "__main__":
    # Listen on 0.0.0.0:8090 (same port as sbitx's my-launcher for
    # cross-box consistency). node-portal owns :80 on the g90, so this
    # MUST be 8090 (or higher).
    #
    # History: commit a461f3b (the waterfall tool) introduced
    # `LAUNCHER_PORT` and set its default to 80, intending to make
    # the g90 launcher the port-80 home page. But the g90's
    # node-portal already owns :80, and the shared launcher's
    # systemd unit was never updated to set LAUNCHER_PORT=80.
    # Result: every g90 that pulled a461f3b crash-looped on
    # "Address already in use" the moment systemd tried to start
    # the launcher. The launcher went down; node-portal kept
    # serving :80. This was undetected in CI because the test
    # sled binds 9090 and the unit file's comment said :8090.
    #
    # Fix: hardcode 8090 here. If a future commit wants the
    # launcher on a different port, update BOTH the g90-shared-
    # launcher.service unit (with Environment=LAUNCHER_PORT=)
    # AND this default. Keep them in sync.
    port = int(os.environ.get("LAUNCHER_PORT", "8090"))
    app.run(host="0.0.0.0", port=port)
