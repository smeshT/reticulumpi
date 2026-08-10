from flask import Flask, render_template, request, redirect
import subprocess
import socket
import os
import time

app = Flask(__name__)


def get_ap_name():
    # AP SSID is the hostname + "-AP" suffix. Read from the box itself
    # so the same code runs unchanged on g90digi, g90f1r2, and any
    # future unit named after its role.
    return f"{socket.gethostname()}-AP"


def get_hostname():
    return socket.gethostname()


def get_lan_ip():
    """Return the box's primary LAN IPv4 address, or None if none.

    Mirrors the launcher's helper. Picks the first non-loopback,
    non-AP, non-ZeroTier IPv4 from `hostname -I`."""
    try:
        out = subprocess.check_output(["hostname", "-I"], text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    for ip in out.split():
        if ip.startswith("127."):
            continue
        if ip.startswith("192.168.4."):
            # AP-only range
            continue
        if ip.startswith("10."):
            # Common ZeroTier range; ZT address is shown separately
            continue
        return ip
    return None


def get_zerotier_ip():
    """Return the box's ZeroTier IPv4 address, or None if not joined.

    The `ip -4 -o addr show` format is `INDEX: IFRNAME<spaces>INET...`
    (only ONE colon, after the index). We split on the first colon
    only and take the rest as the iface name + address data."""
    import re
    try:
        out = subprocess.check_output(
            ["ip", "-4", "-o", "addr", "show"], text=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    for line in out.splitlines():
        if ":" not in line:
            continue
        idx, rest = line.split(":", 1)
        ifname = rest.split()[0] if rest.split() else ""
        if not ifname.startswith("zt"):
            continue
        m = re.search(r"inet (\S+)", rest)
        if m:
            return m.group(1).split("/")[0]
    return None


def get_zerotier_network_id():
    """Return the full 16-hex-char ZT network ID, or None if not joined.

    The .conf file's first line is `v=<protocol-version>`; the
    `nwid=<hex>` line is the second. Read up to 3 lines."""
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


@app.route("/")
def home():
    wifi_status = get_wifi_status()

    meshchat_status=service_status("reticulum-meshchat.service")
    rnsd_status=service_status("reticulumhf-rnsd.service")

    return render_template(
        "index.html",
        wifi_status=wifi_status,
        meshchat_status=meshchat_status,
        rnsd_status=rnsd_status,
        portal_url=get_portal_url(),
        ap_name=get_ap_name(),
        hostname=get_hostname(),
        lan_ip=get_lan_ip(),
        zt_ip=get_zerotier_ip(),
        zt_network_id=get_zerotier_network_id()
    )

def get_meshchat_url():
    ip = get_current_host_ip()
    return f"http://{ip}:8000"

def get_wifi_status():

    try:

        ssid_output = subprocess.check_output(
            [
                "nmcli",
                "-t",
                "-f",
                "ACTIVE,SSID",
                "dev",
                "wifi"
            ],
            text=True
        )

        ip_output = subprocess.check_output(
            [
                "hostname",
                "-I"
            ],
            text=True
        ).strip()

        connected_ssid = "Not connected"
        lan_ip = "Unavailable"

        for line in ssid_output.splitlines():

            if line.startswith("yes:"):

                connected_ssid = line.split(":", 1)[1]

        ip_list = ip_output.split()

        for ip in ip_list:

            if not ip.startswith("192.168.4."):

                lan_ip = ip
                break

        if connected_ssid == "Not connected":

            status = f"""
WiFi Network: Not Connected
Status: AP Only
Browser Address: 192.168.4.1
"""

        else:

            status = f"""
WiFi Network: {connected_ssid}
Status: Connected
Browser Address: {lan_ip}
"""

        return status

    except subprocess.CalledProcessError:

        return "Could not read WiFi status."

def get_portal_url():
    ip = get_current_host_ip()
    return f"http://{ip}:8081"

def service_status(service_name):

    try:

        subprocess.check_output(
            [
                "systemctl",
                "is-active",
                "--quiet",
                service_name
            ]
        )

        return "Running"

    except subprocess.CalledProcessError:

        return "Not Running"

def get_client_wifi_iface():
    """
    Return the wifi device that is NOT the hostapd AP, or None.

    The g90digi image runs hostapd on the onboard wifi (wlan0) as the
    local AP. When a USB wifi dongle is plugged in for client-mode
    scanning/connecting to a home AP, it enumerates as some other iface
    (wlan1 on a clean Bookworm install, wlan2 if something else got
    there first). This helper finds it dynamically so the code does
    not have to hardcode 'wlan1'.

    Detection: nmcli reports the hostapd AP iface as 'unmanaged'
    (NetworkManager doesn't own it). Any other wifi device is the
    client radio. Returns the iface name (e.g. 'wlan1') or None if
    no client radio is present.
    """
    try:
        output = subprocess.check_output(
            [
                "sudo",
                "nmcli",
                "-t",
                "-f",
                "DEVICE,STATE",
                "device",
                "status",
            ],
            text=True,
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError:
        return None

    for line in output.splitlines():
        parts = line.split(":")
        if len(parts) < 2:
            continue
        iface, state = parts[0].strip(), parts[1].strip()
        if not iface.startswith("wlan") and not iface.startswith("wlx"):
            continue
        if state == "unmanaged":
            continue
        return iface

    return None

def get_current_host_ip():
    return request.host.split(":")[0]

def get_shared_launcher_url():
    # The g90 shared launcher is on port 80 (it's the home page). On
    # the nomadpi test sled, the launcher runs on a different port
    # (LAUNCHER_PORT=9090 via systemd Environment); for the wifi
    # page's outbound link we use port 80 since this code lives on
    # the g90 box, not the test sled. If you ever need to point
    # the wifi page at the test sled, change this to read from
    # os.environ.get("SHARED_LAUNCHER_PORT", "80").
    return f"http://{get_current_host_ip()}/"


def get_novnc_url(mode="desktop"):
    ip = get_current_host_ip()

    if mode == "phone":
        return f"http://{ip}:6080/vnc.html?resize=scale&autoconnect=true"

    return f"http://{ip}:6080/vnc.html?resize=remote&autoconnect=true"

@app.route("/scan", methods=["POST"])
def scan():

    client_iface = get_client_wifi_iface()

    if client_iface is None:
        return render_template(
            "index.html",
            message=f"Plug in a USB WiFi adapter to scan for networks. {get_ap_name()}'s onboard WiFi is busy running the local access point.",
            wifi_status=get_wifi_status(),
            portal_url=get_portal_url(),
            ap_name=get_ap_name(),
            hostname=get_hostname(),
            lan_ip=get_lan_ip(),
            zt_ip=get_zerotier_ip(),
            zt_network_id=get_zerotier_network_id()
        )

    try:
        subprocess.check_output(
            [
                "sudo",
                "nmcli",
                "device",
                "set",
                client_iface,
                "managed",
                "yes"
            ],

            text=True,
            stderr=subprocess.STDOUT
        )

        output = subprocess.check_output(
            [
                "sudo",
                "nmcli",
                "-t",
                "-f",
                "SSID",
                "dev",
                "wifi",
                "list",
                "ifname",
                client_iface
            ],
            text=True,
            stderr=subprocess.STDOUT
        )
    except subprocess.CalledProcessError as error:
        return render_template(
            "index.html",
            message="WiFi scan failed.",
            command_output=error.output,
            wifi_status=get_wifi_status(),
            portal_url=get_portal_url(),
            ap_name=get_ap_name(),
            hostname=get_hostname(),
            lan_ip=get_lan_ip(),
            zt_ip=get_zerotier_ip(),
            zt_network_id=get_zerotier_network_id()
        )

    networks = []

    for line in output.splitlines():
        ssid = line.strip()

        if (
            ssid
            and ssid != "ReticulumHF"
            and ssid not in networks
        ):
            networks.append(ssid)

    return render_template(
        "index.html",
        networks=networks,
        message="Scan complete. Select a network.",
        portal_url=get_portal_url(),
        ap_name=get_ap_name(),
        hostname=get_hostname(),
        lan_ip=get_lan_ip(),
        zt_ip=get_zerotier_ip(),
        zt_network_id=get_zerotier_network_id()
    )


@app.route("/connect", methods=["POST"])
def connect():
    ssid = request.form.get("ssid")
    password = request.form.get("password")

    if not ssid:
        return render_template(
            "index.html",
            message="No WiFi network selected.",
            portal_url=get_portal_url(),
            ap_name=get_ap_name(),
            hostname=get_hostname(),
            lan_ip=get_lan_ip(),
            zt_ip=get_zerotier_ip(),
            zt_network_id=get_zerotier_network_id()
        )

    try:
        client_iface = get_client_wifi_iface()

        if client_iface is None:
            return render_template(
                "index.html",
                message="Plug in a USB WiFi adapter before connecting to a network.",
                wifi_status=get_wifi_status(),
                portal_url=get_portal_url(),
                ap_name=get_ap_name(),
                hostname=get_hostname(),
                lan_ip=get_lan_ip(),
                zt_ip=get_zerotier_ip(),
                zt_network_id=get_zerotier_network_id()
            )

        subprocess.check_output(
            [
                "sudo",
                "nmcli",
                "device",
                "set",
                client_iface,
                "managed",
                "yes"
            ],
            text=True,
            stderr=subprocess.STDOUT
        )

        output = subprocess.check_output(
            [
                "sudo",
                "nmcli",
                "dev",
                "wifi",
                "connect",
                ssid,
                "password",
                password,
		"ifname",
		client_iface
            ],
            text=True,
            stderr=subprocess.STDOUT
        )

        output = output.replace("\x1b[2K", "")

        return render_template(
            "index.html",
            wifi_status=get_wifi_status(),
            message="WiFi connected. Connect your device to the same WiFi network, then open the Browser Address shown above.",
            portal_url=get_portal_url(),
            ap_name=get_ap_name(),
            hostname=get_hostname(),
            lan_ip=get_lan_ip(),
            zt_ip=get_zerotier_ip(),
            zt_network_id=get_zerotier_network_id()
       )

    except subprocess.CalledProcessError as error:

        return render_template(
            "index.html",
            wifi_status=get_wifi_status(),
            message="WiFi connection failed.",
            command_output=error.output,
            portal_url=get_portal_url(),
            ap_name=get_ap_name(),
            hostname=get_hostname(),
            lan_ip=get_lan_ip(),
            zt_ip=get_zerotier_ip(),
            zt_network_id=get_zerotier_network_id()
        )

@app.route("/disconnect", methods=["POST"])
def disconnect():

    try:

        client_iface = get_client_wifi_iface()

        if client_iface is None:
            return render_template(
                "index.html",
                message="No USB WiFi adapter to disconnect.",
                wifi_status=get_wifi_status(),
                portal_url=get_portal_url(),
                ap_name=get_ap_name(),
                hostname=get_hostname(),
                lan_ip=get_lan_ip(),
                zt_ip=get_zerotier_ip(),
                zt_network_id=get_zerotier_network_id()
            )

        subprocess.check_output(
            [
                "sudo",
                "nmcli",
                "device",
                "disconnect",
                client_iface
            ],
            text=True,
            stderr=subprocess.STDOUT
        )

        return render_template(
            "index.html",
            message=f"WiFi disconnected. Reconnect to {get_ap_name()} AP at {get_hostname()}.local or 192.168.4.1",
            wifi_status=get_wifi_status(),
            portal_url=get_portal_url(),
            ap_name=get_ap_name(),
            hostname=get_hostname(),
            lan_ip=get_lan_ip(),
            zt_ip=get_zerotier_ip(),
            zt_network_id=get_zerotier_network_id()
        )

    except subprocess.CalledProcessError as error:

        return render_template(
            "index.html",
            message="Failed to disconnect WiFi.",
            command_output=error.output,
            wifi_status=get_wifi_status(),
            portal_url=get_portal_url(),
            ap_name=get_ap_name(),
            hostname=get_hostname(),
            lan_ip=get_lan_ip(),
            zt_ip=get_zerotier_ip(),
            zt_network_id=get_zerotier_network_id()
        )

def process_running(name):
    result = subprocess.run(
        ["pgrep", "-f", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    return result.returncode == 0

@app.route("/apps")
def apps():
    return render_template(
        "apps.html",
        portal_url=get_portal_url(),
        meshchat_url=get_meshchat_url(),
        ap_name=get_ap_name(),
        hostname=get_hostname(),
        lan_ip=get_lan_ip(),
        zt_ip=get_zerotier_ip(),
        zt_network_id=get_zerotier_network_id()
    )
@app.route("/open-meshchat", methods=["POST"])
def open_meshchat():

    subprocess.Popen(
        ["sudo", "/usr/local/bin/start-reticulum-branch"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True        
    )

    return redirect(get_meshchat_url())

@app.route("/restart-meshchat", methods=["POST"])
def restart_meshchat():

    subprocess.Popen(
        ["sudo", "/usr/local/bin/restart-meshchat"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )

    return redirect(get_meshchat_url())

@app.route("/open-reticulum-status", methods=["POST"])
def open_reticulum_status():

    subprocess.Popen(
        ["sudo", "/usr/local/bin/start-reticulum-branch"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )    

    return redirect(get_portal_url())

@app.route("/open-shared-launcher", methods=["POST"])
def open_shared_launcher():
    # Open the g90 shared launcher (FLrig, JS8Call, FLDigi, WSJT-X, Pat
    # Menu, Pavucontrol, MeshChat, Reticulum, etc). Sibling of the
    # sbitx box's my_launcher — same Flask-app pattern, separate code
    # path; the launcher does NOT share state with node-portal.
    return redirect(get_shared_launcher_url())

APPS = {
    "js8call": {
        "process": "js8call",
        "launcher": "/usr/local/bin/start-js8call",
        "help": "js8call.html",
    },
    "fldigi": {
        "process": "fldigi",
        "launcher": "/usr/local/bin/start-fldigi",
        "help": "fldigi.html",
    },
    "flrig": {
        "process": "flrig",
        "launcher": "/usr/local/bin/start-flrig",
        "help": "flrig.html",
    },
    "wsjtx": {
        "process": "wsjtx",
        "launcher": "/usr/local/bin/start-wsjtx",
        "help": "wsjtx.html",
    },
}
@app.route("/start-text-editor", methods=["POST"])
def start_text_editor():

    subprocess.Popen(
        ["sudo", "-u", "pi", "/usr/local/bin/start-text-editor"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )

    time.sleep(1)

    return redirect(get_novnc_url("desktop"))

@app.route("/start-app", methods=["POST"])
def start_app():
    app_name = request.form.get("app")
    mode = request.form.get("screen_mode", "desktop")

    app_info = APPS.get(app_name)

    if not app_info:
        return redirect("/apps")

    if not process_running(app_info["process"]):
        subprocess.Popen(["sudo", "/usr/local/bin/start-digital-branch"])
        subprocess.Popen(["sudo", "-u", "pi", app_info["launcher"]])
        time.sleep(2)

    return redirect(get_novnc_url(mode))

@app.route("/restart-app-help", methods=["POST"])
def restart_app_help():

    app_name = request.form.get("app")
    app_info = APPS.get(app_name)

    if not app_info:
        return redirect("/apps")

    if not process_running(app_info["process"]):

        subprocess.Popen(["sudo", "/usr/local/bin/start-digital-branch"])
        subprocess.Popen(["sudo", "-u", "pi",app_info["launcher"]])
        time.sleep(2)

    return redirect(f"/help/{app_name}")

@app.route("/close-app", methods=["POST"])
def close_app():
    app_name = request.form.get("app")
    app_info = APPS.get(app_name)

    if app_info:
        subprocess.Popen(["pkill", "-f", app_info["process"]])

    return redirect("/apps")

@app.route("/help/<app_name>")
def help_app(app_name):

    app_info = APPS.get(app_name)

    if not app_info:
        return redirect("/apps")
    
    return render_template(app_info["help"])
                           
@app.route("/reset-audio-devices", methods=["POST"])
def reset_audio_devices():

    app_name = request.form.get("app")
    app_info = APPS.get(app_name)

    if app_info:

        if process_running(app_info["process"]):
            subprocess.Popen(["pkill", "-f", app_info["process"]])
            time.sleep(1)

        subprocess.Popen(["sudo", "/usr/local/bin/start-digital-branch"])
        subprocess.Popen(["sudo", "-u", "pi", app_info["launcher"]])
        time.sleep(2)

        return redirect(f"/help/{app_name}")

    return redirect("/apps")

@app.route("/start-pavucontrol", methods=["POST"])
def start_pavucontrol():
    
    app_name = request.form.get("app")
    app_info = APPS.get(app_name)

    subprocess.Popen(
        ["sudo", "-u", "pi", "/usr/local/bin/start-pavucontrol"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )

    time.sleep(2)

    if app_info:
        subprocess.Popen(["pkill", "-f", app_info["process"]])
        time.sleep(1)

        subprocess.Popen(["sudo", "/usr/local/bin/start-digital-branch"])
        subprocess.Popen(["sudo", "-u", "pi", app_info["launcher"]])

    time.sleep(2)    

    return redirect(f"/help/{app_name}")

@app.route("/shutdown", methods=["POST"])
def shutdown():
    subprocess.Popen(["sudo", "shutdown", "-h", "now"])
    return """
    <html>
    <body>
        <h2>Shutting down...</h2>
        <p>You may now safely remove power after the Pi fully stops.</p>
    </body>
    </html>
    """

@app.route("/reboot", methods=["POST"])
def reboot():
    subprocess.Popen(["sudo", "reboot"])
    return """
    <html>
    <body>
        <h2>Rebooting...</h2>
        <p>The system will restart shortly. 
        <br> Click back to return to the apps page. 
        <br> Do not refresh this page.</p>
    </body>
    </html>
        """

# node-portal is the wifi setup / admin page. The shared launcher is
# the home page at :80. We were on :80 originally, which made the
# launcher URL require a ":8090" port suffix everywhere. Flipping the
# roles (launcher :80, wifi :8090) means the user can bookmark
# http://<host>/ for the launcher and reach the wifi page by typing
# the port when needed. The wifi page is admin-only (network changes,
# LAN reconfig); the launcher is the daily-driver UI.
app.run(host="0.0.0.0", port=8090)
