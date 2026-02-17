import subprocess
import json
import time
from datetime import datetime

class SpeedTest:
    def __init__(self):
        self.results = {}
    
    def run_command(self, cmd):
        """Führe Shell-Kommando aus"""
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "", "Timeout nach 60s", 1
        except Exception as e:
            return "", str(e), 1
    
    def check_internet(self):
        """Prüfe Internet-Verbindung"""
        print("Prüfe Internet-Verbindung...")
        stdout, stderr, code = self.run_command("ping -c 3 8.8.8.8")
        return code == 0
    
    def run_speedtest(self):
        """Führe Speedtest durch"""
        if not self.check_internet():
            print("Keine Internet-Verbindung!")
            return None
        
        print("Starte Speedtest (kann 30-60s dauern)...")
        stdout, stderr, code = self.run_command("speedtest-cli --json --source $(ip -4 addr show wlan0 | grep -oP '(?<=inet\\s)\\d+(\\.\\d+){3}')")
        
        if code != 0:
            print(f"Speedtest-Fehler: {stderr}")
            return None
        
        try:
            data = json.loads(stdout)
            self.results = {
                "timestamp": datetime.now().isoformat(),
                "download_mbps": round(data.get("download", 0) / 1_000_000, 2),
                "upload_mbps": round(data.get("upload", 0) / 1_000_000, 2),
                "ping_ms": data.get("ping", 0),
                "server": data.get("server", {}).get("name", "Unbekannt"),
                "isp": data.get("client", {}).get("isp", "Unbekannt")
            }
            return self.results
        except Exception as e:
            print(f"Fehler beim Parsen der Speedtest-Daten: {e}")
            return None
    
    def save_results(self, filename="speedtest_results.json"):
        """Speichere Ergebnisse"""
        try:
            # Vorherige Ergebnisse laden (falls vorhanden)
            try:
                with open(filename, 'r') as f:
                    all_results = json.load(f)
            except FileNotFoundError:
                all_results = {"tests": []}
            
            # Neues Ergebnis hinzufügen
            all_results["tests"].append(self.results)
            
            # Speichern
            with open(filename, 'w') as f:
                json.dump(all_results, f, indent=2)
            
            print(f"Speedtest-Ergebnis in {filename} gespeichert")
        except Exception as e:
            print(f"Fehler beim Speichern: {e}")
    
    def print_results(self):
        """Zeige Ergebnisse an"""
        if not self.results:
            print("Keine Ergebnisse vorhanden")
            return
        
        print("\\n=== Speedtest-Ergebnis ===")
        print(f"Download: {self.results['download_mbps']} Mbps")
        print(f"Upload:   {self.results['upload_mbps']} Mbps")
        print(f"Ping:     {self.results['ping_ms']} ms")
        print(f"Server:   {self.results['server']}")
        print(f"ISP:      {self.results['isp']}")

def main():
    tester = SpeedTest()
    result = tester.run_speedtest()
    
    if result:
        tester.print_results()
        tester.save_results()
    else:
        print("Speedtest fehlgeschlagen")

if __name__ == "__main__":
    main()
