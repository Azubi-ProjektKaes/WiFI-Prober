# Füge diese Funktionen hinzu:

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
    except:
        pass
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

# Neue API-Endpoints hinzufügen:

@app.route('/api/wlan0_ip')
def api_wlan0_ip():
    """Gibt die aktuelle wlan0 IP-Adresse zurück"""
    ip = get_wlan0_ip()
    return jsonify({"ip": ip, "interface": "wlan0"})

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
