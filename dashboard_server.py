#!/usr/bin/env python3

from flask import Flask, render_template, jsonify
from flask_cors import CORS
import json
import subprocess
import threading
import time
import re
import psutil
import socket
import fcntl
import struct
from datetime import datetime, timedelta
from pathlib import Path

app = Flask(__name__)
CORS(app)

RESULTS_FILE = "/home/azubi/wifi_probe_results.json"
SCAN_IN_PROGRESS = False

current_live_data = {
    "ping": {
        "google": {"avg_ms": 0, "success": False},
        "cloudflare": {"avg_ms": 0, "success": False}
    },
    "system": {
        "cpu": 0,
        "ram": 0,
        "temp": 0,
        "disk": 0
    }
}

last_incident = {
    "active": False,
    "type": None,
    "since": None,
    "message": None,
    "severity": None
}


def get_ip_address(ifname: str) -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        return socket.inet_ntoa(fcntl.ioctl(
            s.fileno(),
            0x8915,
            struct.pack('256s', (ifname + '\0')[:15].encode('utf-8'))
        )[20:24])
    except OSError:
        return "unknown"


def load_results():
    try:
        if Path(RESULTS_FILE).exists():
            with open(RESULTS_FILE, 'r') as f:
                return json.load(f)
        return {"probe_results": []}
    except Exception as e:
        print(f"Fehler beim Laden der Ergebnisse: {e}")
        return {"probe_results": []}


def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return round(int(f.read()) / 1000, 1)
    except:
        return 0


def run_single_ping(target):
    try:
        cmd = ['ping', '-I', 'wlan0', '-c', '1', '-W', '1', target]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            cmd = ['ping', '-c', '1', '-W', '1', target]
            result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            match = re.search(r'time=([\d.]+)', result.stdout)
            if match:
                val = float(match.group(1))
                return {"avg_ms": val, "success": True}
    except:
        pass
    return {"avg_ms": 0, "success": False}


def register_incident(typ, msg, severity="critical"):
    global last_incident
    if not last_incident["active"]:
        last_incident = {
            "active": True,
            "type": typ,
            "since": datetime.now().isoformat(timespec="seconds"),
            "message": msg,
            "severity": severity
        }


def clear_incident():
    global last_incident
    last_incident = {
        "active": False,
        "type": None,
        "since": None,
        "message": None,
        "severity": None
    }


def background_worker():
    targets = {"google": "8.8.8.8", "cloudflare": "1.1.1.1"}
    print("Live-Worker gestartet (Ping & System Stats)...")
    while True:
        any_ping_fail = False
        for name, ip in targets.items():
            res = run_single_ping(ip)
            current_live_data["ping"][name] = res
            if not res["success"]:
                any_ping_fail = True
        try:
            current_live_data["system"]["cpu"] = psutil.cpu_percent(interval=None)
            current_live_data["system"]["ram"] = psutil.virtual_memory().percent
            current_live_data["system"]["disk"] = psutil.disk_usage('/').percent
            current_live_data["system"]["temp"] = get_cpu_temp()
        except Exception as e:
            print(f"Fehler bei System-Stats: {e}")
        if any_ping_fail:
            register_incident("ping", "Live-Ping zu mindestens einem Ziel fehlgeschlagen", "warning")
        else:
            if last_incident["active"] and last_incident["type"] == "ping":
                clear_incident()
        time.sleep(1)


worker = threading.Thread(target=background_worker, daemon=True)
worker.start()


@app.route('/')
def dashboard():
    return render_template('dashboard.html')


@app.route('/api/ping_multi')
def api_ping_multi():
    meta = {
        "hostname": socket.gethostname(),
        "wlan_ip": get_ip_address("wlan0")
    }
    return jsonify({
        "ping": current_live_data["ping"],
        "system": current_live_data["system"],
        "meta": meta,
        "incident": last_incident
    })


@app.route('/api/stats')
def api_stats():
    data = load_results()
    results = data.get("probe_results", [])
    if not results:
        return jsonify({})
    cutoff = datetime.now() - timedelta(hours=24)
    recent = [r for r in results if datetime.fromisoformat(r["timestamp"].replace("Z", "")) > cutoff]
    wifi_counts = [r.get("wifi_scan", {}).get("networks_found", 0) for r in recent]
    avg_wifi = sum(wifi_counts) / len(wifi_counts) if wifi_counts else 0
    speeds = []
    for r in recent:
        st = r.get("speedtest", {})
        if "download_mbps" in st:
            speeds.append(st["download_mbps"])
    avg_speed = sum(speeds) / len(speeds) if speeds else 0
    return jsonify({
        "total_probes": len(results),
        "probes_24h": len(recent),
        "avg_wifi_networks": round(avg_wifi, 1),
        "avg_download_speed": round(avg_speed, 2),
        "last_probe": results[-1]["timestamp"]
    })


@app.route('/api/networks')
def api_networks():
    data = load_results()
    results = data.get("probe_results", [])
    cutoff = datetime.now() - timedelta(hours=24)
    networks = {}
    for r in results:
        try:
            ts = datetime.fromisoformat(r["timestamp"].replace("Z", ""))
            if ts < cutoff:
                continue
        except:
            continue
        scan = r.get("wifi_scan", {}).get("networks", [])
        for net in scan:
            ssid = net.get("essid", "")
            if not ssid:
                continue
            if ssid not in networks:
                networks[ssid] = {
                    "ssid": ssid,
                    "first_seen": r["timestamp"],
                    "last_seen": r["timestamp"],
                    "max_signal": net.get("signal", -100),
                    "encryption": net.get("encryption", "Unknown"),
                    "count": 1
                }
            else:
                networks[ssid]["last_seen"] = r["timestamp"]
                networks[ssid]["count"] += 1
                if net.get("signal", -100) > networks[ssid]["max_signal"]:
                    networks[ssid]["max_signal"] = net.get("signal", -100)
    return jsonify({"networks": list(networks.values())})


@app.route('/api/chart/speedtest/<int:hours>')
def api_chart_speedtest(hours):
    data = load_results()
    results = data.get("probe_results", [])
    cutoff = datetime.now() - timedelta(hours=hours)
    timestamps, downloads, uploads = [], [], []
    for r in results:
        if datetime.fromisoformat(r["timestamp"].replace("Z", "")) > cutoff:
            st = r.get("speedtest", {})
            if "download_mbps" in st:
                timestamps.append(r["timestamp"])
                downloads.append(st["download_mbps"])
                uploads.append(st.get("upload_mbps", 0))
    return jsonify({"timestamps": timestamps, "downloads": downloads, "uploads": uploads})


@app.route('/api/chart/wifi/<int:hours>')
def api_chart_wifi(hours):
    data = load_results()
    results = data.get("probe_results", [])
    cutoff = datetime.now() - timedelta(hours=hours)
    timestamps, counts = [], []
    for r in results:
        if datetime.fromisoformat(r["timestamp"].replace("Z", "")) > cutoff:
            timestamps.append(r["timestamp"])
            counts.append(r.get("wifi_scan", {}).get("networks_found", 0))
    return jsonify({"timestamps": timestamps, "network_counts": counts})


@app.route('/api/chart/ping/<int:hours>')
def api_chart_ping(hours):
    data = load_results()
    results = data.get("probe_results", [])
    cutoff = datetime.now() - timedelta(hours=hours)
    timestamps, google_pings, cloudflare_pings = [], [], []
    for r in results:
        try:
            if datetime.fromisoformat(r["timestamp"].replace("Z", "")) <= cutoff:
                continue
            ping_data = r.get("ping", {})
            g_val = None
            c_val = None
            if ping_data:
                g = ping_data.get("google", {})
                c = ping_data.get("cloudflare", {})
                if g.get("success"):
                    g_val = g.get("avg_ms")
                if c.get("success"):
                    c_val = c.get("avg_ms")
            if g_val is not None or c_val is not None:
                timestamps.append(r["timestamp"])
                google_pings.append(g_val)
                cloudflare_pings.append(c_val)
        except:
            continue
    return jsonify({"timestamps": timestamps, "google": google_pings, "cloudflare": cloudflare_pings})


@app.route('/api/scan/trigger', methods=['POST'])
def api_scan_trigger():
    global SCAN_IN_PROGRESS
    if SCAN_IN_PROGRESS:
        return jsonify({"status": "busy", "message": "Scan läuft bereits"}), 429

    def run_restart():
        global SCAN_IN_PROGRESS
        SCAN_IN_PROGRESS = True
        try:
            subprocess.run(["sudo", "systemctl", "restart", "wifi-prober.service"], timeout=10)
            time.sleep(20)
        finally:
            SCAN_IN_PROGRESS = False

    t = threading.Thread(target=run_restart, daemon=True)
    t.start()
    return jsonify({"status": "started", "message": "Scan ausgelöst"})


@app.route('/api/scan/status')
def api_scan_status():
    return jsonify({"scanning": SCAN_IN_PROGRESS})


@app.route('/api/health')
def api_health():
    return jsonify({"status": "ok", "message": "System online"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
