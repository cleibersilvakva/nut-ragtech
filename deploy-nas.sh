#!/usr/bin/env bash
# Rodar no NAS (192.168.50.110) como root ou via sudo
set -e

echo "=== Deploy NUT Client (NAS) ==="

# 1. Instalar nut-client
if command -v apt-get &>/dev/null; then
    apt-get install -y nut-client
elif command -v opkg &>/dev/null; then
    opkg install nut-client
else
    echo "ERRO: gerenciador de pacotes não reconhecido. Instale o nut-client manualmente."
    exit 1
fi
echo "[OK] nut-client instalado"

# 2. nut.conf — modo netclient
cat > /etc/nut/nut.conf <<'EOF'
MODE=netclient
EOF
echo "[OK] /etc/nut/nut.conf"

# 3. upsmon.conf
cat > /etc/nut/upsmon.conf <<'EOF'
MONITOR ragtech@192.168.50.57 1 upsmon_nas CHANGE_ME_NAS secondary
MINSUPPLIES 1
SHUTDOWNCMD "/sbin/shutdown -h +0"
POLLFREQ 5
POLLFREQALERT 5
HOSTSYNC 15
DEADTIME 15
FINALDELAY 5
EOF
chown root:nut /etc/nut/upsmon.conf 2>/dev/null || true
chmod 640 /etc/nut/upsmon.conf
echo "[OK] /etc/nut/upsmon.conf"

# 4. Habilitar e iniciar nut-monitor
systemctl enable --now nut-monitor
sleep 2

echo ""
echo "=== Status ==="
systemctl is-active nut-monitor && echo "nut-monitor: active" || echo "nut-monitor: FALHOU"
echo ""
echo "=== Teste de conexão ==="
upsc ragtech@192.168.50.57 2>/dev/null | grep -E "ups.status|battery.charge|input.voltage" \
    || echo "ERRO: não conseguiu conectar em 192.168.50.57 — verifique firewall/porta 3493"
