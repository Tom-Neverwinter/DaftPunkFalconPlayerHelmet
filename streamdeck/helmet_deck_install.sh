#!/bin/bash
# Installs the Stream Deck wrist controller on the helmet FPP. Safe to re-run.
# Upload helmet_deck.py + this file to FPP > Content Setup > File Manager > Scripts, then Run this one.
set -e
SRC=/home/fpp/media/scripts
# ponytail: Debian's packaged lib, FPP's image has no pip3
sudo apt-get install -y python3-pil libhidapi-libusb0 python3-elgato-streamdeck
sudo install -m 755 "$SRC/helmet_deck.py" /usr/local/bin/helmet_deck.py
# Elgato vendor id: let the deck be opened without root
echo 'SUBSYSTEMS=="usb", ATTRS{idVendor}=="0fd9", TAG+="uaccess", MODE="0666"' | sudo tee /etc/udev/rules.d/70-streamdeck.rules >/dev/null
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo tee /etc/systemd/system/helmet-deck.service >/dev/null <<'EOF'
[Unit]
Description=Stream Deck wrist controller for FPP
After=fppd.service network.target

[Service]
User=fpp
ExecStart=/usr/bin/python3 /usr/local/bin/helmet_deck.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now helmet-deck
sudo systemctl restart helmet-deck
python3 /usr/local/bin/helmet_deck.py --selftest
lsusb | grep -i 0fd9 || echo "No Stream Deck on USB yet; plug it in, the service picks it up within 3 s."
systemctl --no-pager status helmet-deck | head -5
