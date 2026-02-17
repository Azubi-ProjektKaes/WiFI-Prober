#!/usr/bin/env python3
import subprocess
import re
import json
import time
from datetime import datetime

class WiFiScanner:
    def __init__(self):
        self.interface = "wlan0"
        self.scan_results = []
    
    def run_command(self, cmd):
        """Führe Shell-Kommando aus"""
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "", "Timeout", 1
        except Exception as e:
            return "", str(e), 1
    
    def scan_networks(self):
        """Scanne nach WiFi-Netzwerken"""
        print(f"Scanne WiFi-Netzwerke auf {self.interface}...")
        
        # Interface aktivieren
        stdout, stderr, code = self.run_command(f"sudo ip link set {self.interface} up")
        if code != 0:
            print(f"Fehler beim Aktivieren von {self.interface}: {stderr}")
            return []
        
        # Scan durchführen
        stdout, stderr, code = self.run_command(f"sudo iwlist {self.interface} scan")
        if code != 0:
            print(f"Scan-Fehler: {stderr}")
            return []
        
        networks = self.parse_scan_results(stdout)
        
        # NEU: Deduplizierung nach SSID
        if networks:
            print(f"Raw-Scan: {len(networks)} Einträge gefunden")
            networks = self.deduplicate_by_ssid(networks)
            print(f"Nach Deduplizierung: {len(networks)} unique SSIDs")
        
        return networks
    
    def parse_scan_results(self, scan_output):
        """Parse iwlist scan Ausgabe"""
        networks = []
        current_network = {}
        
        for line in scan_output.split('\n'):
            line = line.strip()
            
            # Neues Netzwerk
            if "Cell" in line and "Address:" in line:
                if current_network:
                    networks.append(current_network)
                current_network = {
                    "timestamp": datetime.now().isoformat(),
                    "bssid": "",
                    "essid": "",
                    "signal": 0,
                    "frequency": "",
                    "encryption": "Open"
                }
                
                # MAC-Adresse extrahieren
                mac_match = re.search(r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', line)
                if mac_match:
                    current_network["bssid"] = mac_match.group(0)
            
            # ESSID (Netzwerk-Name)
            elif "ESSID:" in line:
                essid_match = re.search(r'ESSID:"([^"]*)"', line)
                if essid_match:
                    current_network["essid"] = essid_match.group(1)
            
            # Signal-Stärke
            elif "Signal level=" in line:
                signal_match = re.search(r'Signal level=(-?\d+)', line)
                if signal_match:
                    current_network["signal"] = int(signal_match.group(1))
            
            # Frequenz
            elif "Frequency:" in line:
                freq_match = re.search(r'Frequency:([0-9.]+) GHz', line)
                if freq_match:
                    current_network["frequency"] = freq_match.group(1) + " GHz"
            
            # Verschlüsselung
            elif "Encryption key:on" in line:
                current_network["encryption"] = "WEP/WPA"
            elif "WPA" in line:
                current_network["encryption"] = "WPA/WPA2"
        
        # Letztes Netzwerk hinzufügen
        if current_network:
            networks.append(current_network)
        
        return networks
    
    def deduplicate_by_ssid(self, networks):
        """Dedupliziere Netzwerke nach ESSID, behalte stärkstes Signal"""
        unique = {}
        
        for net in networks:
            ssid = net.get("essid", "")
            if not ssid or ssid == "":
                continue  # Überspringe leere SSIDs
            
            # Wenn SSID noch nicht gesehen oder aktuelles Signal stärker
            if ssid not in unique or net["signal"] > unique[ssid]["signal"]:
                unique[ssid] = net
        
        return list(unique.values())
    
    def save_results(self, networks, filename="wifi_scan.json"):
        """Speichere Ergebnisse in JSON-Datei"""
        try:
            with open(filename, 'w') as f:
                json.dump({
                    "scan_time": datetime.now().isoformat(),
                    "interface": self.interface,
                    "networks_found": len(networks),
                    "networks": networks
                }, f, indent=2)
            print(f"Ergebnisse in {filename} gespeichert")
        except Exception as e:
            print(f"Fehler beim Speichern: {e}")
    
    def print_results(self, networks):
        """Zeige Ergebnisse an"""
        print(f"\n=== {len(networks)} WiFi-Netzwerke gefunden ===")
        for i, net in enumerate(networks, 1):
            print(f"{i:2}. {net['essid']:<20} | {net['signal']:3} dBm | {net['encryption']:<8} | {net['bssid']}")

def main():
    scanner = WiFiScanner()
    networks = scanner.scan_networks()
    
    if networks:
        scanner.print_results(networks)
        scanner.save_results(networks)
    else:
        print("Keine Netzwerke gefunden oder Fehler beim Scannen")

if __name__ == "__main__":
    main()
