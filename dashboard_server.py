#!/usr/bin/env python3
from flask import Flask, render_template, jsonify
from flask_cors import CORS
import json
import subprocess
import threading
import time
import re
import psutil
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

def load_results():
    """Lade gespeicherte Probe-Ergebnisse"""
    try:
        if Path(RESULTS_FILE).exists():
            with open(RESULTS_FILE, 'r') as f:
                return json.load(f)
        return {"probe_results": []}
    except Exception as e:
        print(f"Fehler beim Laden der Ergebnisse: {e}")
        return {"probe_results": []}

def get_cpu_temp():
    """Holt CPU Temperatur"""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return round(int(f.read()) / 1000, 1)
    except:
        return 0

def get_wlan0_ip():
    """Holt die IP-Adresse des wlan0 Interfaces"""
    try:
        result = subprocess.run(
            ['ip', '-4', 'addr', 'show', 'wlan0'],
            capture_output=True, text=True, timeout=5
        )
        match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', result.stdout)
        if match:
            return match.group(1)
    except Exception as e:
        print(f"Fehler beim Holen der wlan0 IP: {e}")
    return "Nicht verfügbar"

def detect_wifi_outages(results):
    """Erkennt Ausfälle basierend auf Ping/Speedtest-Fehlern"""
    outages = []
    for i, r in enumerate(results):
        ping_google = r.get("ping", {}).get("google", {})
        ping_cloudflare = r.get("ping", {}).get("cloudflare", {})
        speedtest = r.get("speedtest", {})
        
        # Ausfall erkennen wenn beide Pings fehlschlagen ODER Speedtest Error
        ping_fail = not ping_google.get("success", False) and not ping_cloudflare.get("success", False)
        speedtest_fail = "error" in speedtest
        
        if ping_fail or speedtest_fail:
            outages.append({
                "timestamp": r["timestamp"],
                "reason": "Kein Ping" if ping_fail else "Speedtest fehlgeschlagen",
                "index": i
            })
    return outages

def run_single_ping(target):
    """Führt einzelnen Ping aus"""
    try:
        # Versuche Ping über wlan0
        cmd = ['ping', '-I', 'wlan0', '-c', '1', '-W', '1', target]
        result = subprocess.run(cmd, capture_output=True, text=True)
        # Fallback ohne Interface-Bindung falls wlan0 fehlschlägt
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

def background_worker():
    """Hintergrund-Thread für Live-Daten"""
    targets = {"google": "8.8.8.8", "cloudflare": "1.1.1.1"}
    print("Live-Worker gestartet (Ping & System Stats)...")
    while True:
        for name, ip in targets.items():
            res = run_single_ping(ip)
            current_live_data["ping"][name] = res
        try:
            current_live_data["system"]["cpu"] = psutil.cpu_percent(interval=None)
            current_live_data["system"]["ram"] = psutil.virtual_memory().percent
            current_live_data["system"]["disk"] = psutil.disk_usage('/').percent
            current_live_data["system"]["temp"] = get_cpu_temp()
        except Exception as e:
            print(f"Fehler bei System-Stats: {e}")
        time.sleep(1)

# Starte Background-Worker
worker = threading.Thread(target=background_worker, daemon=True)
worker.start()

@app.route('/')
def dashboard():
    """Hauptseite Dashboard"""
    return render_template('dashboard.html')

@app.route('/api/ping_multi')
def api_ping_multi():
    """Live Ping Daten"""
    return jsonify(current_live_data)

@app.route('/api/stats')
def api_stats():
    """Statistik Übersicht"""
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
        "last_probe": results[-1]["timestamp"] if results else ""
    })

@app.route('/api/wlan0_ip')
def api_wlan0_ip():
    """Gibt die aktuelle wlan0 IP-Adresse zurück"""
    ip = get_wlan0_ip()
    return jsonify({"ip": ip, "interface": "wlan0", "status": "ok" if ip != "Nicht verfügbar" else "error"})

@app.route('/api/outages')
def api_outages():
    """Gibt WiFi-Ausfälle der letzten 24h zurück"""
    data = load_results()
    results = data.get("probe_results", [])
    cutoff = datetime.now() - timedelta(hours=24)
    
    recent = []
    for r in results:
        try:
            ts = datetime.fromisoformat(r["timestamp"].replace("Z", ""))
            if ts > cutoff:
                recent.append(r)
        except:
            continue
    
    outages = detect_wifi_outages(recent)
    total_probes = len(recent)
    outage_count = len(outages)
    availability = round((1 - outage_count / total_probes) * 100, 1) if total_probes > 0 else 100
    
    return jsonify({
        "outages": outages,
        "outage_count": outage_count,
        "total_probes": total_probes,
        "availability_percent": availability
    })

@app.route('/api/networks')
def api_networks():
    """Alle gefundenen WiFi Netzwerke"""
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
    """Speedtest Chart Daten"""
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
    """WiFi Netzwerk Chart Daten"""
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
    """Ping Latenz Chart Daten"""
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
                if g.get("success"): g_val = g.get("avg_ms")
                if c.get("success"): c_val = c.get("avg_ms")
            if g_val is not None or c_val is not None:
                timestamps.append(r["timestamp"])
                google_pings.append(g_val)
                cloudflare_pings.append(c_val)
        except:
            continue
    
    return jsonify({"timestamps": timestamps, "google": google_pings, "cloudflare": cloudflare_pings})

@app.route('/api/scan/trigger', methods=['POST'])
def api_scan_trigger():
    """Manuellen Scan auslösen"""
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
    """Scan Status"""
    return jsonify({"scanning": SCAN_IN_PROGRESS})

@app.route('/api/health')
def api_health():
    """Health Check"""
    return jsonify({"status": "ok", "message": "System online"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
