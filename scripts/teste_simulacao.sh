#!/bin/bash
# Simulação completa de queda de energia — sem desligar o nobreak fisicamente
# Uso: sudo bash teste_simulacao.sh
#
# Sequência:
#   1. Para ragtech-monitor (evita sobrescrever valores simulados)
#   2. Simula OB (queda de energia)
#   3. Simula OB LB (bateria crítica) → NAS deve desligar
#   4. Aguarda NAS ficar offline
#   5. Restaura OL (energia voltou) → WOL enviado automaticamente
#   6. Aguarda NAS responder ao ping
#   7. Reinicia ragtech-monitor

NUT_USER="admin"
NUT_PASS="ragtech_admin_2024"
UPS="ragtech@127.0.0.1"
NAS_IP="192.168.50.110"

rw() { upsrw -s "$1=$2" -u "$NUT_USER" -p "$NUT_PASS" "$UPS" 2>/dev/null; }

echo "[1/6] Pausando ragtech-monitor..."
systemctl stop ragtech-monitor
sleep 2

echo "[2/6] Simulando queda de energia (OB)..."
rw ups.status "OB"
rw input.voltage "0.0"
sleep 10

echo "[3/6] Simulando bateria crítica (OB LB) — NAS vai desligar..."
rw ups.status "OB LB"
rw battery.charge "20"
sleep 2

echo "      Aguardando NAS desligar (máx 120s)..."
TIMEOUT=120
ELAPSED=0
while ping -c 1 -W 2 "$NAS_IP" > /dev/null 2>&1; do
    sleep 5
    ELAPSED=$((ELAPSED + 5))
    echo "      NAS ainda online... ${ELAPSED}s"
    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
        echo "ERRO: NAS não desligou em ${TIMEOUT}s. Abortando."
        rw ups.status "OL"
        rw battery.charge "100"
        rw input.voltage "220.0"
        systemctl start ragtech-monitor
        exit 1
    fi
done
echo "      NAS OFFLINE. Aguardando 15s para garantir shutdown completo..."
sleep 15

echo "[4/6] Simulando retorno da energia (OL)..."
echo "      (notifycmd.py enviará Telegram + WOL automaticamente)"
rw ups.status "OL"
rw battery.charge "100"
rw input.voltage "220.0"
sleep 6

echo "[5/6] Aguardando NAS ligar via WOL (máx 120s)..."
ELAPSED=0
while ! ping -c 1 -W 2 "$NAS_IP" > /dev/null 2>&1; do
    sleep 5
    ELAPSED=$((ELAPSED + 5))
    echo "      NAS ainda offline... ${ELAPSED}s"
    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
        echo "AVISO: NAS não respondeu em ${TIMEOUT}s. Verifique WOL no NAS."
        break
    fi
done

if ping -c 1 -W 2 "$NAS_IP" > /dev/null 2>&1; then
    echo "      NAS ONLINE!"
fi

echo "[6/6] Retomando ragtech-monitor..."
systemctl start ragtech-monitor
sleep 3
systemctl status ragtech-monitor --no-pager | head -5

echo ""
echo "=== TESTE CONCLUIDO ==="
upsc "$UPS" | grep -E "ups.status|battery.charge|input.voltage"
