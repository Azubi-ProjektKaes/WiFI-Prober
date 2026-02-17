#!/bin/bash

echo ">>> Starte Update..."

# 1. Code aktualisieren
git pull origin main

# 2. Falls sich was an den Requirements geändert hat (optional, aber sicher)
# sudo pip3 install -r requirements.txt --break-system-packages

# 3. Services neustarten (damit der neue Code geladen wird)
echo ">>> Starte Services neu..."
sudo systemctl restart wifi-prober.service
sudo systemctl restart wifi-dashboard.service

echo ">>> Update fertig! System läuft mit neuer Version."
