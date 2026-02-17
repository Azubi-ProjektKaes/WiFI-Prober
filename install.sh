#!/bin/bash

# Abbrechen bei Fehlern
set -e

echo ">>> Starte Installation der WiFi Probing Station..."

# 1. System-Updates & Abhängigkeiten
echo ">>> Installiere System-Pakete..."
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv wireless-tools iw speedtest-cli git

# 2. Python Libraries installieren
echo ">>> Installiere Python Libraries..."
# Hinweis: Auf neueren Pis (Bookworm) muss man oft --break-system-packages nutzen oder venv
# Wir nutzen hier die globale Installation der Einfachheit halber
sudo pip3 install flask flask-cors psutil --break-system-packages

# 3. Ordnerstruktur erstellen
echo ">>> Erstelle Ordner..."
INSTALL_DIR="/home/azubi/wifi-prober"
mkdir -p "$INSTALL_DIR/templates"

# 4. Dateien kopieren (Annahme: Du führst das Skript aus dem Ordner aus, wo die Dateien liegen)
echo ">>> Kopiere Dateien..."
cp wifi_prober_v2.py "$INSTALL_DIR/"
cp dashboard_server.py "$INSTALL_DIR/"
cp wifi_scanner.py "$INSTALL_DIR/"
cp speedtest_runner.py "$INSTALL_DIR/"
cp templates/dashboard.html "$INSTALL_DIR/templates/"

# Rechte setzen
chmod +x "$INSTALL_DIR/"*.py
chown -R azubi:azubi "$INSTALL_DIR"

# 5. Systemd Services erstellen
echo ">>> Richte Autostart ein..."

# Prober Service
cat << EOF | sudo tee /etc/systemd/system/wifi-prober.service
[Unit]
Description=WiFi Prober Service
After=network.target

[Service]
User=azubi
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/wifi_prober_v2.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Dashboard Service
cat << EOF | sudo tee /etc/systemd/system/wifi-dashboard.service
[Unit]
Description=WiFi Dashboard Server
After=network.target

[Service]
User=azubi
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/dashboard_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 6. Services aktivieren & starten
echo ">>> Starte Services..."
sudo systemctl daemon-reload
sudo systemctl enable wifi-prober.service
sudo systemctl enable wifi-dashboard.service
sudo systemctl restart wifi-prober.service
sudo systemctl restart wifi-dashboard.service

echo ">>> Installation abgeschlossen! Dashboard unter http://$(hostname -I | awk '{print $1}'):5000"
