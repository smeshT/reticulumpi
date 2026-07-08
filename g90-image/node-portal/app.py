from flask import Flask, render_template, request, redirect
import subprocess
import time

app = Flask(__name__)


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
        portal_url=get_portal_url()
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
    
def get_current_host_ip():
    return request.host.split(":")[0]

def get_shared_launcher_url():
    # The g90 shared launcher (sibling of the sbitx box's my_launcher)
    # is served by /home/pi/shared_launcher/app.py via systemd unit
    # g90-shared-launcher.service, listening on :8090. node-portal runs
    # on :80, so the link must include the explicit port.
    return f"http://{get_current_host_ip()}:8090/"


def get_novnc_url(mode="desktop"):
    ip = get_current_host_ip()

    if mode == "phone":
        return f"http://{ip}:6080/vnc.html?resize=scale&autoconnect=true"

    return f"http://{ip}:6080/vnc.html?resize=remote&autoconnect=true"

@app.route("/scan", methods=["POST"])
def scan():

    subprocess.check_output(
        [
            "sudo",
            "nmcli",
            "device",
            "set",
            "wlan1",
            "managed",
            "yes"
        ],

        text=True,
        stderr=subprocess.STDOUT
    )

    output = subprocess.check_output(
        ["sudo","nmcli", "-t", "-f", "SSID", "dev", "wifi"],
        text=True
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
        portal_url=get_portal_url()
    )


@app.route("/connect", methods=["POST"])
def connect():
    ssid = request.form.get("ssid")
    password = request.form.get("password")

    if not ssid:
        return render_template(
            "index.html",
            message="No WiFi network selected.",
            portal_url=get_portal_url()
        )

    try:
        subprocess.check_output(
            [
                "sudo",
                "nmcli",
                "device",
                "set",
                "wlan1",
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
		"wlan1"
            ],
            text=True,
            stderr=subprocess.STDOUT
        )

        output = output.replace("\x1b[2K", "")

        return render_template(
            "index.html",
            wifi_status=get_wifi_status(),
            message="WiFi connected. Connect your device to the same WiFi network, then open the Browser Address shown above.",
            portal_url=get_portal_url()
       )

    except subprocess.CalledProcessError as error:

        return render_template(
            "index.html",
            wifi_status=get_wifi_status(),
            message="WiFi connection failed.",
            command_output=error.output,
            portal_url=get_portal_url()
        )

@app.route("/disconnect", methods=["POST"])
def disconnect():

    try:

        subprocess.check_output(
            [
                "sudo",
                "nmcli",
                "device",
                "disconnect",
                "wlan1"
            ],
            text=True,
            stderr=subprocess.STDOUT
        )

        return render_template(
            "index.html",
            message="WiFi disconnected. Reconnect to g90digi AP at g90digi.local or 192.168.4.1",
            wifi_status=get_wifi_status(),
            portal_url=get_portal_url()
        )

    except subprocess.CalledProcessError as error:

        return render_template(
            "index.html",
            message="Failed to disconnect WiFi.",
            command_output=error.output,
            wifi_status=get_wifi_status(),
            portal_url=get_portal_url()
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
        meshchat_url=get_meshchat_url()
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

app.run(host="0.0.0.0", port=80)
