#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ "$(id -u)" = 0 ] || { echo 'Execute com sudo.'; exit 1; }
python3 -B -m unittest -v test_daily_report
python3 -B -c 'from pathlib import Path; s=Path("/opt/ragtech-monitor/ragtech_nut.py").read_text(); assert "parse_mode=None" in s, "Instale a correção dos avisos de boot primeiro"'
systemd-analyze verify raspberry-daily-report.service raspberry-daily-report.timer
backup=/opt/ragtech-monitor/backup-daily-report-$(date +%Y%m%d-%H%M%S)
mkdir -m 700 "$backup"
for item in /opt/ragtech-monitor/raspberry_daily_report.py /etc/systemd/system/raspberry-daily-report.service /etc/systemd/system/raspberry-daily-report.timer; do
    if [ -f "$item" ]; then cp -p "$item" "$backup/"; fi
done
install -d -m 700 /var/lib/ragtech-monitor
install -m 644 raspberry_daily_report.py /opt/ragtech-monitor/raspberry_daily_report.py
install -m 644 raspberry-daily-report.service /etc/systemd/system/raspberry-daily-report.service
install -m 644 raspberry-daily-report.timer /etc/systemd/system/raspberry-daily-report.timer
systemctl daemon-reload
systemctl enable --now raspberry-daily-report.timer
echo "Relatório diário agendado. Backup: $backup"
