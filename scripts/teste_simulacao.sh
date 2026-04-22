#!/bin/bash
# Simulação completa de queda de energia — sem desligar o nobreak fisicamente
# Uso: sudo bash teste_simulacao.sh
#
# Sequência:
#   0. Garante estado limpo (limpa FSD anterior)
#   1. Para ragtech-monitor (evita sobrescrever valores simulados)
#   2. Simula OB (queda de energia)
#   3. Simula OB LB (bateria crítica) → NAS deve desligar
#   4. Aguarda NAS ficar offline
#   5. Restaura OL e inicia ragtech-monitor → detecta OB→OL → clear_fsd + WOL automático
#   6. Aguarda NAS responder ao ping

NUT_USER="admin"
NUT_PASS="CHANGE_ME_ADMIN"
UPS="ragtech@127.0.0.1"
NAS_IP="192.168.50.110"
TIMEOUT=300

rw() { upsrw -s "$1=$2" -u "$NUT_USER" -p "$NUT_PASS" "$UPS" 2>/dev/null; }

_abort() {
    echo "ERRO: $1. Limpando estado..."
    rw ups.status "OL"
    rw battery.charge "100"
    rw input.voltage "220.0"
    systemctl stop nut-monitor nut-server
    systemctl stop nut-driver@ragtech
    sleep 2
    systemctl start nut-driver@ragtech && sleep 2
    systemctl start nut-server && sleep 2
    systemctl start nut-monitor && sleep 2
    systemctl start ragtech-monitor
    exit 1
}

echo "[0/6] Garantindo estado limpo (limpa FSD anterior)..."
systemctl stop nut-monitor ragtech-monitor 2>/dev/null
systemctl stop nut-server 2>/dev/null
systemctl stop nut-driver@ragtech 2>/dev/null
sleep 2
systemctl start nut-driver@ragtech && sleep 2
systemctl start nut-server && sleep 2
systemctl start nut-monitor && sleep 3
STATUS=$(upsc $UPS 2>/dev/null | grep '^ups.status' | awk '{print $2}')
echo "      ups.status: $STATUS"
[ "$STATUS" = "OL" ] || _abort "Estado inicial não é OL: $STATUS"

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

echo "      Aguardando NAS desligar (máx ${TIMEOUT}s)..."
ELAPSED=0
while ping -c 1 -W 2 "$NAS_IP" > /dev/null 2>&1; do
    sleep 5
    ELAPSED=$((ELAPSED + 5))
    echo "      NAS ainda online... ${ELAPSED}s"
    [ "$ELAPSED" -ge "$TIMEOUT" ] && _abort "NAS não desligou em ${TIMEOUT}s"
done
echo "      NAS OFFLINE. Aguardando 15s para garantir shutdown completo..."
sleep 15

echo "[4/6] Energia voltou (OL) — iniciando ragtech-monitor..."
echo "      ragtech_nut.py detectará OB→OL e disparará: clear_fsd + WOL automaticamente"
rw ups.status "OL"
rw battery.charge "100"
rw input.voltage "220.0"
# Inicia ragtech-monitor: na 1ª leitura verá OL no hardware mas last_status=None
# Na 2ª leitura verá OL e last_status=OL → sem transição ainda
# Para forçar a detecção OB→OL no teste, inicializamos last_status via arquivo de estado
echo "OB LB" > /tmp/ragtech_last_status
systemctl start ragtech-monitor
sleep 3

echo "[5/6] Aguardando NAS ligar via WOL (máx ${TIMEOUT}s)..."
echo "      (ragtech_nut.py enviará WOL após bateria >= 80% e FSD limpo)"
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

ping -c 1 -W 2 "$NAS_IP" > /dev/null 2>&1 && echo "      NAS ONLINE!" || true

echo "[6/6] Verificando serviços..."
sleep 3
systemctl status ragtech-monitor --no-pager | head -5

echo ""
echo "=== TESTE CONCLUIDO ==="
upsc "$UPS" | grep -E "ups.status|battery.charge|input.voltage"
