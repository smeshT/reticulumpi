from flask import Flask, render_template, redirect, url_for, request
import subprocess

app = Flask(__name__)

SCRIPTS = "/home/pi/shared_launcher/scripts"

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
            ["git", "-C", "/home/pi/shared_launcher",
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
            ["git", "-C", "/home/pi/shared_launcher",
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
    }
    return render_template(
        "index.html",
        status=status,
        host=request.host.split(":")[0],
        vnc_ws_port=VNC_WS_PORT,
        version=_get_launcher_version(),
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
        ["git", "-C", "/home/pi/shared_launcher",
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
         "g90-shared-launcher.service"],
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
    # Listen on 0.0.0.0:8090. Same port as the sbitx box's my-launcher so
    # the experience is consistent across the two boxes (and bookmarks work
    # the same). The g90 box's noVNC is on 6080 (vs sbitx 6100); the index
    # template embeds vnc_ws_port so the VNC tab link matches.
    app.run(host="0.0.0.0", port=8090)
