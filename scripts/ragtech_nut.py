#!/usr/bin/env python3
"""
Ragtech Easy Pro — NUT bridge daemon.

Le o nobreak via protocolo binario proprietario (USB serial, 2400 baud)
e atualiza o NUT em tempo real via upsrw (dummy-ups driver).

Tambem detecta transicoes OB→OL e dispara a sequencia de recuperacao:
  Telegram + aguarda bateria >= WOL_MIN_BAT + limpa FSD + WOL para o NAS.

Instalar em: /opt/ragtech-monitor/ragtech_nut.py
"""
import serial
import subprocess
import threading
import time
import logging
import sys
import urllib.request
import urllib.parse

PORT          = "/dev/ttyACM0"
CMD           = bytes.fromhex("AA0400801E9E")
POLL_SEC      = 5
UPS_NAME      = "ragtech@127.0.0.1"
NUT_USER      = "admin"
NUT_PASS      = "CHANGE_ME_ADMIN"

BOT_TOKEN     = "CHANGE_ME_TELEGRAM_BOT_TOKEN"
CHAT_ID       = "CHANGE_ME_TELEGRAM_CHAT_ID"
NAS_MAC       = "6c:1f:f7:a8:b1:0d"
WOL_BROADCAST     = "192.168.50.255"
WOL_MIN_BAT       = 80
STATE_FILE        = "/tmp/ragtech_last_status"
NAS_IP            = "192.168.50.110"
NAS_CHECK_INTERVAL = 30  # segundos entre pings ao NAS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

_recovery_lock = threading.Lock()


def read_ups() -> dict | None:
    try:
        s = serial.Serial(PORT, 2400, timeout=2)
        s.reset_input_buffer()
        s.write(CMD)
        time.sleep(0.5)
        resp = s.read(64)
        s.close()

        if len(resp) < 31 or resp[0] != 0xAA:
            log.warning("Resposta invalida: %s", resp.hex())
            return None

        battery_pct = round(resp[0x08] * 0.392)
        battery_v   = round(resp[0x0B] * 0.0671, 1)
        input_v     = round(resp[0x0C] * 1.06,   1)
        current_a   = round(resp[0x0D] * 0.1152, 1)
        load_pct    = resp[0x0E]
        temp_c      = resp[0x0F]
        output_v    = round(resp[0x1E] * 0.555,  1)

        on_battery  = input_v < 50.0
        low_battery = battery_pct < 25

        status = "OB" if on_battery else "OL"
        if on_battery and low_battery:
            status += " LB"

        return {
            "battery.charge":  str(battery_pct),
            "battery.voltage": str(battery_v),
            "input.voltage":   str(input_v),
            "output.voltage":  str(output_v),
            "ups.load":        str(load_pct),
            "ups.temperature": str(temp_c),
            "output.current":  str(current_a),
            "ups.status":      status,
        }
    except Exception as exc:
        log.error("Erro ao ler UPS: %s", exc)
        return None


def upsrw(key: str, value: str) -> bool:
    result = subprocess.run(
        ["upsrw", "-s", f"{key}={value}", "-u", NUT_USER, "-p", NUT_PASS, UPS_NAME],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        log.debug("upsrw %s=%s: %s", key, value, result.stderr.strip())
        return False
    return True


def push_to_nut(data: dict) -> None:
    for key, value in data.items():
        upsrw(key, value)


def send_telegram(text: str) -> None:
    payload = urllib.parse.urlencode({
        "chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"
    }).encode()
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                data=payload,
            ),
            timeout=10,
        )
    except Exception as exc:
        log.warning("Telegram falhou: %s", exc)


def ping_nas() -> bool:
    result = subprocess.run(
        ["ping", "-c", "1", "-W", "2", NAS_IP],
        capture_output=True
    )
    return result.returncode == 0


def send_wol() -> None:
    for _ in range(3):
        subprocess.run(["wakeonlan", "-i", WOL_BROADCAST, NAS_MAC], capture_output=True)
        time.sleep(2)
    log.info("WOL enviado para %s via %s", NAS_MAC, WOL_BROADCAST)


def clear_fsd() -> None:
    """Reinicia a stack NUT para limpar o flag FSD do dummy-ups."""
    log.info("Limpando FSD — reiniciando stack NUT...")
    for svc in ["nut-monitor", "nut-server"]:
        subprocess.run(["systemctl", "stop", svc], capture_output=True)
    subprocess.run(["systemctl", "stop", "nut-driver@ragtech"], capture_output=True)
    time.sleep(2)
    subprocess.run(["systemctl", "start", "nut-driver@ragtech"], capture_output=True)
    time.sleep(2)
    subprocess.run(["systemctl", "start", "nut-server"], capture_output=True)
    time.sleep(2)
    subprocess.run(["systemctl", "start", "nut-monitor"], capture_output=True)
    time.sleep(3)
    log.info("Stack NUT reiniciada — FSD limpo")


def power_restored_sequence() -> None:
    """Executado em thread separada quando energia volta (OB→OL)."""
    with _recovery_lock:
        log.info("Energia voltou — iniciando sequencia de recuperacao")
        send_telegram(
            f"✅ *Energia voltou*\nNobreak retornou à rede elétrica.\n"
            f"Aguardando bateria ≥ {WOL_MIN_BAT}% para ligar o NAS..."
        )

        # Aguarda bateria atingir WOL_MIN_BAT
        bat = 0
        for _ in range(120):  # max 120 iteracoes de 60s = 2h
            data = read_ups()
            if data:
                push_to_nut(data)
                bat = int(data["battery.charge"])
                log.info("Aguardando bateria: %d%%/%d%%", bat, WOL_MIN_BAT)
                if bat >= WOL_MIN_BAT:
                    break
            time.sleep(60)

        # Limpa FSD e reinicia stack NUT
        clear_fsd()

        # Liga o NAS via WOL
        log.info("Enviando WOL para NAS (bateria: %d%%)", bat)
        send_telegram(
            f"🔌 *Ligando NAS via WOL*\nBateria em *{bat}%*. Enviando magic packet..."
        )
        send_wol()


def load_last_status() -> str | None:
    try:
        with open(STATE_FILE) as f:
            return f.read().strip() or None
    except FileNotFoundError:
        return None


def save_last_status(status: str) -> None:
    try:
        with open(STATE_FILE, "w") as f:
            f.write(status)
    except Exception as exc:
        log.warning("Nao foi possivel salvar estado: %s", exc)


def main() -> None:
    log.info("Iniciando monitor Ragtech Easy Pro -> %s", UPS_NAME)
    last_status = load_last_status()
    if last_status:
        log.info("Estado anterior carregado: %s", last_status)
    recovery_thread = None
    last_nas_online = None
    nas_check_counter = 0

    while True:
        data = read_ups()
        if data:
            push_to_nut(data)
            status = data["ups.status"]

            if status != last_status:
                log.info(
                    "Status: %s | Bateria: %s%% | Entrada: %sV | Carga: %s%%",
                    status,
                    data["battery.charge"],
                    data["input.voltage"],
                    data["ups.load"],
                )

                # Detecta transicao OB→OL (energia voltou)
                if (last_status is not None
                        and "OB" in last_status
                        and "OB" not in status):
                    if recovery_thread is None or not recovery_thread.is_alive():
                        recovery_thread = threading.Thread(
                            target=power_restored_sequence, daemon=True
                        )
                        recovery_thread.start()

                last_status = status
                save_last_status(status)
        else:
            log.warning("Falha na leitura, tentando em %ss...", POLL_SEC)

        # Monitoramento do NAS
        nas_check_counter += POLL_SEC
        if nas_check_counter >= NAS_CHECK_INTERVAL:
            nas_check_counter = 0
            nas_online = ping_nas()
            if last_nas_online is None:
                last_nas_online = nas_online  # inicializa sem notificar
            elif nas_online != last_nas_online:
                if nas_online:
                    log.info("NAS voltou online")
                    send_telegram("✅ *NAS online*\nO NAS voltou a responder na rede.")
                else:
                    log.warning("NAS ficou offline")
                    send_telegram("🔴 *NAS offline*\nO NAS parou de responder ao ping.")
                last_nas_online = nas_online

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
