[README.md](https://github.com/user-attachments/files/25361485/README.md)

📡 WiFi Probing Station
Ein leichtgewichtiges, Raspberry Pi-basiertes Monitoring-System zur kontinuierlichen Überwachung von WLAN-Netzwerken, Internet-Geschwindigkeit und Netzwerklatenz.

🚀 Features
Live-Dashboard: Modernes Web-Interface (Dark/Light Mode) mit Echtzeit-Daten.

Latenz-Monitoring: Kontinuierliche Ping-Messungen zu Google (8.8.8.8) und Cloudflare (1.1.1.1). Optimiert, um Bufferbloat durch Speedtests zu vermeiden.

WLAN-Scanner: Erfasst Umgebungsvariablen wie Signalstärke (dBm) und Verschlüsselungstypen.

Internet-Speedtest: Periodische Messung von Bandbreite (Down/Up) via speedtest-cli.

System-Status: Überwachung von CPU-Last, RAM-Verbrauch und Temperatur des Raspberry Pi.

JSON-Historie: Speichert die letzten 24h an Daten lokal für historische Analysen.

📋 Voraussetzungen
Hardware: Raspberry Pi (3B+, 4 oder 5 empfohlen für akkurate Speedtests) mit WLAN-Modul.

OS: Raspberry Pi OS (Lite oder Desktop).

Software: Python 3, pip, git, wireless-tools.

🛠 Installation
Repository klonen:

bash
git clone https://github.com/Azubi-ProjektKaes/WiFI-Prober.git
cd wifi-prober
Installation starten:
Das Installationsskript richtet alle Abhängigkeiten ein und erstellt die systemd-Services.

bash
chmod +x install.sh
./install.sh
Dashboard aufrufen:
Öffne deinen Browser und gehe zu:
http://<IP-DEINES-PI>:5000

⚙️ Konfiguration & WLAN
Der Prober nutzt das Standard-Interface wlan0. Stelle sicher, dass der Raspberry Pi mit dem gewünschten WLAN verbunden ist.

🔐 Anleitung: Verbindung mit Hidden SSID (Verstecktes WLAN)
Da der Raspberry Pi versteckte Netzwerke nicht automatisch im Scan sieht, muss die Verbindung manuell erzwungen werden.

Methode 1: Über nmcli (NetworkManager - Empfohlen)

Führe folgenden Befehl aus (ersetze SSID und PASSWORT):

bash
sudo nmcli device wifi connect "DEINE-SSID" password "DEIN-PASSWORT" hidden yes
Wichtig: Das hidden yes am Ende ist entscheidend!

Möglicherweise muss es auch so expliziet eingestellt werden:

bash
sudo nmcli con add type wifi ifname wlan0 con-name "MeinWLAN" ssid "DEIN-NETZWERKNAME"

sudo nmcli con modify "MeinWLAN" wifi-sec.key-mgmt wpa-psk

sudo nmcli con modify "MeinWLAN" wifi-sec.psk "DEIN-PASSWORT"

sudo nmcli con modify "MeinWLAN" wifi.hidden yes

sudo nmcli con up "MeinWLAN"

Methode 2: Über wpa_supplicant (Legacy/Headless)

Öffne die Konfiguration:

bash
sudo nano /etc/wpa_supplicant/wpa_supplicant.conf
Füge folgenden Block hinzu (scan_ssid=1 ist der Schlüssel für hidden Networks):

text
network={
    ssid="DEINE-SSID"
    scan_ssid=1
    psk="DEIN-PASSWORT"
    key_mgmt=WPA-PSK
}
Speichern (STRG+O, Enter, STRG+X) und Netzwerk neu laden:

bash
sudo wpa_cli -i wlan0 reconfigure


📂 Projektstruktur
dashboard_server.py: Flask-Server, der die Web-Oberfläche und API bereitstellt.

wifi_prober_v2.py: Hauptlogik für das Sammeln der Daten (Ping, Scan, Speedtest).

wifi_scanner.py: Wrapper für Systemaufrufe zum Scannen der WiFi-Umgebung.

templates/dashboard.html: Frontend-Code (HTML/JS/Chart.js).

install.sh: Setup-Skript für automatisiertes Deployment.

