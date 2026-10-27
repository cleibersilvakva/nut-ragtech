#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ "$(id -u)" = 0 ] || { echo 'Execute com sudo.'; exit 1; }
python3 -B -m unittest -v test_lifecycle test_patch
expected=$(sha256sum /opt/ragtech-monitor/ragtech_nut.py)
expected=${expected%% *}
actual=$(sha256sum /opt/ragtech-monitor/ragtech_nut.py)
actual=${actual%% *}
[ "$expected" = "$actual" ] || { echo 'Produção mudou; revisar antes de instalar.'; exit 1; }
stamp=$(date +%Y%m%d-%H%M%S)
backup=/opt/ragtech-monitor/backup-boot-notice-$stamp
mkdir -m 700 "$backup"
cp -p /opt/ragtech-monitor/ragtech_nut.py "$backup/"
if [ -f /opt/ragtech-monitor/raspberry_lifecycle.py ]; then
    cp -p /opt/ragtech-monitor/raspberry_lifecycle.py "$backup/"
fi
install -d -m 700 /var/lib/ragtech-monitor
install -m 644 raspberry_lifecycle.py /opt/ragtech-monitor/raspberry_lifecycle.py
python3 -B patch_monitor.py /opt/ragtech-monitor/ragtech_nut.py
python3 -B -c 'import ast, sys; from pathlib import Path; sys.path.insert(0, "/opt/ragtech-monitor"); import raspberry_lifecycle; ast.parse(Path("/opt/ragtech-monitor/ragtech_nut.py").read_text())'
systemctl restart ragtech-monitor.service
sleep 5
if ! systemctl is-active --quiet ragtech-monitor.service; then
    cp -p "$backup/ragtech_nut.py" /opt/ragtech-monitor/ragtech_nut.py
    systemctl restart ragtech-monitor.service
    echo "Instalação falhou; daemon anterior restaurado. Backup: $backup"
    exit 1
fi
echo "Instalado. Backup: $backup"
echo 'Reboot planejado: sudo python3 /opt/ragtech-monitor/raspberry_lifecycle.py --reboot "motivo"'
