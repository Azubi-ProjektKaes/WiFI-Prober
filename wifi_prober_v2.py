#!/usr/bin/env python3
import json
import time
import logging
import signal
import subprocess
import re
from datetime import datetime, timedelta
from pathlib import Path
from wifi_scanner import WiFiScanner
from speedtest_runner import SpeedTest

class WiFiProberV2:
    def __init__(self, config_file="wifi_config.json"):
        self.config = self.load_config(config_file)
        self.setup_logging()
        self.scanner = WiFiScanner()
        self.speedtest = SpeedTest()
        self.running = True
        self.interface = self.config.get("wifi", {}).get("interface", "wlan0")
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        self.logger.info("WiFi Probing Station v2 initialisiert")
    
    def load_config(self, config_file):
        """Lade Konfiguration"""
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warnung: {config_file} nicht gefunden, verwende Defaults")
            return self.get_default_config()
        except Exception as e:
            print(f"Fehler beim Laden der Konfiguration: {e}")
            return self.get_default_config()
    
    def get_default_config(self):
        """Standard Konfiguration"""
        return {
            "general": {"probe_interval_seconds": 300, "max_stored_results": 1000, "log_level": "INFO"},
            "wifi": {"interface": "wlan0", "scan_timeout_seconds": 30, "known_networks": []},
            "speedtest": {"enabled": True, "timeout_seconds": 60, "server_id": None},
            "monitoring": {"nagios_enabled": False, "checkmk_enabled": False, "alert_on_no_internet": True, "alert_on_low_speed_mbps": 10}
        }
    
    def setup_logging(self):
        """Logging einrichten"""
        log_level = getattr(logging, self.config["general"]["log_level"], logging.INFO)
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('/home/azubi/wifi_prober.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger('WiFiProber')
    
    def signal_handler(self, signum, frame):
        """Signal Handler für graceful shutdown"""
        self.logger.info(f"Signal {signum} empfangen, stoppe graceful...")
        self.running = False
    
    def run_ping(self, target):
        """Führe Ping aus"""
        try:
            # Versuche Ping über das konfigurierte Interface
            cmd = ['ping', '-I', self.interface, '-c', '1', '-W', '2', target]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            # Fallback: Falls Interface-Bind fehlschlägt, versuche normalen Ping
            if result.returncode != 0:
                cmd = ['ping', '-c', '1', '-W', '2', target]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                match = re.search(r'time=([\d.]+)', result.stdout)
                if match:
                    return {"avg_ms": float(match.group(1)), "success": True}
        except Exception as e:
            self.logger.debug(f"Ping Fehler zu {target}: {e}")
            pass
        return {"avg_ms": 0, "success": False}
    
    def run_probe_cycle(self):
        """Führe einen kompletten Probe-Zyklus aus"""
        self.logger.info("Starte Probe-Zyklus")
        try:
            # 1. ZUERST Ping (auf ruhiger Leitung) - VERMEIDET BUFFERBLOAT SPIKES
            ping_google = self.run_ping("8.8.8.8")
            ping_cloudflare = self.run_ping("1.1.1.1")
            self.logger.info(f"Ping Google: {ping_google['avg_ms']}ms, Cloudflare: {ping_cloudflare['avg_ms']}ms")
            
            # 2. DANN WiFi Scan
            networks = self.scanner.scan_networks()
            self.logger.info(f"{len(networks)} WiFi-Netzwerke gefunden")
            
            # 3. ZULETZT Speedtest (da dieser die Leitung voll auslastet)
            speedtest_result = None
            if self.config["speedtest"]["enabled"]:
                speedtest_result = self.speedtest.run_speedtest()
                if speedtest_result:
                    self.logger.info(f"Speedtest: {speedtest_result['download_mbps']} Mbps down")
            
            result = {
                "timestamp": datetime.now().isoformat(),
                "wifi_scan": {"networks_found": len(networks), "networks": networks},
                "speedtest": speedtest_result if speedtest_result else {"error": "Deaktiviert oder fehlgeschlagen"},
                "ping": {
                    "google": ping_google,
                    "cloudflare": ping_cloudflare
                },
                "system_info": self.get_system_info()
            }
            
            self.save_result(result)
            self.check_alerts(result)
            return result
        except Exception as e:
            self.logger.error(f"Fehler im Probe-Zyklus: {e}")
            return None
    
    def get_system_info(self):
        """Holt System-Informationen"""
        return {
            "timestamp": datetime.now().isoformat(),
            "uptime": self.get_uptime(),
            "memory_usage": self.get_memory_usage(),
            "wifi_interface_status": self.get_wifi_status(),
            "wifi_ip_address": self.get_wifi_ip()
        }
    
    def get_uptime(self):
        """Holt System Uptime"""
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.readline().split()[0])
                return str(timedelta(seconds=int(uptime_seconds)))
        except:
            return "Unbekannt"
    
    def get_memory_usage(self):
        """Holt RAM Auslastung"""
        try:
            with open('/proc/meminfo', 'r') as f:
                lines = f.readlines()
                total = int([line for line in lines if 'MemTotal' in line][0].split()[1])
                available = int([line for line in lines if 'MemAvailable' in line][0].split()[1])
                used_percent = round((total - available) / total * 100, 1)
                return f"{used_percent}%"
        except:
            return "Unbekannt"
    
    def get_wifi_status(self):
        """Holt WiFi Verbindungsstatus"""
        try:
            result = subprocess.run(['iwconfig', self.interface], capture_output=True, text=True)
            if 'ESSID:off' in result.stdout:
                return "Nicht verbunden"
            if 'ESSID:' in result.stdout:
                # Zusätzlich IP prüfen
                ip_result = subprocess.run(
                    ['ip', '-4', 'addr', 'show', self.interface],
                    capture_output=True, text=True
                )
                if 'inet ' in ip_result.stdout:
                    return "Verbunden mit IP"
                return "Verbunden ohne IP"
            return "Interface down"
        except:
            return "Unbekannt"
    
    def get_wifi_ip(self):
        """Holt die IP-Adresse des WiFi Interfaces"""
        try:
            result = subprocess.run(
                ['ip', '-4', 'addr', 'show', self.interface],
                capture_output=True, text=True
            )
            match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', result.stdout)
            if match:
                return match.group(1)
        except:
            pass
        return None
    
    def save_result(self, result):
        """Speichert Ergebnis in JSON-Datei"""
        results_file = "/home/azubi/wifi_probe_results.json"
        try:
            if Path(results_file).exists():
                with open(results_file, 'r') as f:
                    data = json.load(f)
            else:
                data = {"probe_results": []}
            
            data["probe_results"].append(result)
            
            # Maximale Anzahl Ergebnisse begrenzen
            max_results = self.config["general"]["max_stored_results"]
            if len(data["probe_results"]) > max_results:
                data["probe_results"] = data["probe_results"][-max_results:]
            
            with open(results_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.error(f"Fehler beim Speichern: {e}")
    
    def check_alerts(self, result):
        """Prüft auf Alert-Bedingungen"""
        monitoring = self.config["monitoring"]
        
        if monitoring["alert_on_no_internet"]:
            speedtest = result.get("speedtest", {})
            if "error" in speedtest:
                self.logger.warning("ALERT: Keine Internet-Verbindung verfügbar")
                self.send_alert("Keine Internet-Verbindung", "WiFi Prober kann keine Internet-Geschwindigkeit messen")
        
        if monitoring.get("alert_on_low_speed_mbps", 0) > 0:
            speedtest = result.get("speedtest", {})
            if "download_mbps" in speedtest and speedtest["download_mbps"] < monitoring["alert_on_low_speed_mbps"]:
                self.logger.warning(f"ALERT: Niedrige Internet-Geschwindigkeit: {speedtest['download_mbps']} Mbps")
                self.send_alert(
                    "Niedrige Internet-Geschwindigkeit",
                    f"Download-Speed: {speedtest['download_mbps']} Mbps (Limit: {monitoring['alert_on_low_speed_mbps']} Mbps)"
                )
    
    def send_alert(self, title, message):
        """Sendet Alert in Log-Datei"""
        self.logger.info(f"ALERT: {title} - {message}")
        alert_data = {"timestamp": datetime.now().isoformat(), "title": title, "message": message}
        with open("/home/azubi/alerts.json", "a") as f:
            f.write(json.dumps(alert_data) + "\n")
    
    def run(self):
        """Hauptschleife"""
        interval = self.config["general"]["probe_interval_seconds"]
        self.logger.info(f"Starte WiFi Probing Station (Intervall: {interval}s)")
        
        while self.running:
            self.run_probe_cycle()
            if self.running:
                time.sleep(interval)
        
        self.logger.info("WiFi Probing Station gestoppt")

def main():
    prober = WiFiProberV2()
    prober.run()

if __name__ == "__main__":
    main()
