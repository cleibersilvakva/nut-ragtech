#!/usr/bin/env bash
set -e
REPO=/home/cleibersilva/Dev/nut-ragtech

echo "=== Deploy NUT/Ragtech ==="

# 1. Configs NUT
sudo cp "$REPO/configs/nut.conf"           /etc/nut/nut.conf
sudo cp "$REPO/configs/upsd.conf"          /etc/nut/upsd.conf
sudo cp "$REPO/configs/ups.conf"           /etc/nut/ups.conf
sudo cp "$REPO/configs/upsd.users"         /etc/nut/upsd.users
sudo cp "$REPO/configs/upsmon-server.conf" /etc/nut/upsmon.conf
sudo cp "$REPO/configs/ragtech.dev"        /etc/nut/ragtech.dev

sudo chown root:nut /etc/nut/{nut,upsd,ups,upsmon,ragtech.dev}.conf \
    /etc/nut/upsd.users /etc/nut/ragtech.dev 2>/dev/null || \
sudo chown root:nut /etc/nut/nut.conf /etc/nut/upsd.conf /etc/nut/ups.conf \
    /etc/nut/upsd.users /etc/nut/upsmon.conf /etc/nut/ragtech.dev
sudo chmod 640 /etc/nut/nut.conf /etc/nut/upsd.conf /etc/nut/ups.conf \
    /etc/nut/upsd.users /etc/nut/upsmon.conf /etc/nut/ragtech.dev

echo "[OK] /etc/nut/"

# 2. notifycmd.py
sudo cp "$REPO/scripts/notifycmd.py" /etc/nut/notifycmd.py
sudo chown root:nut /etc/nut/notifycmd.py
sudo chmod 750 /etc/nut/notifycmd.py
echo "[OK] /etc/nut/notifycmd.py"

# 3. ragtech_nut.py
sudo mkdir -p /opt/ragtech-monitor
sudo cp "$REPO/scripts/ragtech_nut.py" /opt/ragtech-monitor/ragtech_nut.py
sudo chown root:root /opt/ragtech-monitor/ragtech_nut.py
sudo chmod 755 /opt/ragtech-monitor/ragtech_nut.py
echo "[OK] /opt/ragtech-monitor/ragtech_nut.py"

# 4. Systemd units
sudo cp "$REPO/systemd/ragtech-monitor.service"   /etc/systemd/system/
sudo mkdir -p /etc/systemd/system/nut-server.service.d
sudo cp "$REPO/systemd/nut-server-network-wait.conf" \
    /etc/systemd/system/nut-server.service.d/network-wait.conf
sudo mkdir -p /etc/systemd/system/nut-monitor.service.d
sudo cp "$REPO/systemd/nut-monitor-restart.conf" \
    /etc/systemd/system/nut-monitor.service.d/restart.conf
sudo systemctl daemon-reload
echo "[OK] systemd"

# 5. Iniciar serviços
sudo systemctl enable --now nut-driver@ragtech
sleep 2
sudo systemctl enable --now nut-server
sleep 2
sudo systemctl enable --now nut-monitor
sleep 2
sudo systemctl enable --now ragtech-monitor

echo ""
echo "=== Status ==="
systemctl is-active nut-driver@ragtech nut-server nut-monitor ragtech-monitor
echo ""
echo "=== upsc ==="
upsc ragtech@127.0.0.1 2>/dev/null | grep -E "ups.status|battery.charge|input.voltage" || echo "(aguardar daemon iniciar)"
