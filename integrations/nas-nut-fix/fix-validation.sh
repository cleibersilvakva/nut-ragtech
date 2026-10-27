#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ "$(id -u)" = 0 ] || { echo 'Execute com sudo.'; exit 1; }
python3 -B -m unittest -v test_validation_guard
backup=/var/backups/nas-nut-validation-$(date +%Y%m%d-%H%M%S)
install -d -m 700 "$backup"
cp -p /etc/systemd/system/nas-nut-validation.service "$backup/"
install -m 644 validation_guard.py /opt/nas-nut-client/validation_guard.py
install -m 644 nas-nut-validation.service /etc/systemd/system/nas-nut-validation.service
systemd-analyze verify /etc/systemd/system/nas-nut-validation.service
systemctl daemon-reload
# Harmless test of the exact stop/test/restore flow, before authorizing real poweroff.
python3 -B /opt/nas-nut-client/validation_guard.py
systemctl is-active nas-nut-client.service
systemctl reset-failed nas-nut-validation.service
printf '%s\n' 'Correção e teste inofensivo concluídos; cliente de produção restaurado. Nenhum desligamento real executado.'
