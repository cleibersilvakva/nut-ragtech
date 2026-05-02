#!/usr/bin/env python3
"""
Ragtech Easy Pro — NUT bridge daemon.

Le o nobreak via protocolo binario proprietario (USB serial, 2400 baud)
e atualiza o NUT em tempo real via upsrw (dummy-ups driver).

Tambem detecta transicoes OB→OL e dispara a sequencia de recuperacao:
  Telegram + aguarda bateria >= WOL_MIN_BAT + limpa FSD + WOL para o NAS.

Instalar em: /opt/ragtech-monitor/ragtech_nut.py
"""
import json
import re
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
NUT_PASS      = "ragtech_admin_2024"

BOT_TOKEN     = "8469193508:AAFoFGamn4SeITRGy-u3_iS5C7x54Q0Vxe4"
CHAT_ID       = "915551687"
NAS_MAC       = "6c:1f:f7:a8:b1:0d"
WOL_BROADCAST     = "192.168.50.255"
WOL_MIN_BAT       = 80
STATE_FILE        = "/tmp/ragtech_last_status"
NAS_IP            = "192.168.50.110"
NAS_CHECK_INTERVAL = 30
INTERNET_HOSTS    = ["8.8.8.8", "1.1.1.1"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

_recovery_lock = threading.Lock()
_ups_data_lock = threading.Lock()
_last_ups_data: dict | None = None


def get_cached_ups() -> dict | None:
    with _ups_data_lock:
        return _last_ups_data.copy() if _last_ups_data else None


def set_cached_ups(data: dict) -> None:
    global _last_ups_data
    with _ups_data_lock:
        _last_ups_data = data


def read_ups() -> dict | None:
    try:
        s = serial.Serial(PORT, 2400, timeout=2)
        s.reset_input_buffer()
        s.write(CMD)
        time.sleep(0.5)
        resp = s.read(64)
        s.close()

        # Protocolo retorna 30 ou 31 bytes; 0x1E (output_v) so existe em 31+
        if len(resp) < 30 or resp[0] != 0xAA:
            log.warning("Resposta invalida: %s", resp.hex())
            return None

        battery_pct = round(resp[0x08] * 0.392)
        battery_v   = round(resp[0x0B] * 0.0671, 1)
        input_v     = round(resp[0x0C] * 1.06,   1)
        current_a   = round(resp[0x0D] * 0.1152, 1)
        load_pct    = resp[0x0E]
        temp_c      = resp[0x0F]
        output_v    = round(resp[0x1E] * 0.555,  1) if len(resp) > 0x1E else 0.0

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


def check_internet_latency() -> tuple[bool, float]:
    for host in INTERNET_HOSTS:
        result = subprocess.run(
            ["ping", "-c", "3", "-W", "3", host],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            m = re.search(r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)/", result.stdout)
            avg = float(m.group(1)) if m else 0.0
            return True, avg
    return False, 0.0


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

        clear_fsd()

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


# ---------------------------------------------------------------------------
# Handlers de comandos Telegram (#nut / #net)
# ---------------------------------------------------------------------------

def handle_nut_command() -> None:
    data = get_cached_ups()
    if not data:
        send_telegram("⚠️ *Nobreak* — falha na leitura do dispositivo")
        return
    status = data["ups.status"]
    if status == "OL":
        emoji = "🟢"
        status_text = "Na rede elétrica"
    elif "LB" in status:
        emoji = "🔴"
        status_text = "Bateria fraca"
    else:
        emoji = "🟡"
        status_text = "Na bateria"
    send_telegram(
        f"{emoji} *Nobreak — Status Atual*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Status:   *{status_text}* (`{status}`)\n"
        f"Bateria:  *{data['battery.charge']}%* ({data['battery.voltage']}V)\n"
        f"Entrada:  *{data['input.voltage']}V*\n"
        f"Saída:    *{data['output.voltage']}V*\n"
        f"Carga:    *{data['ups.load']}%*\n"
        f"Corrente: *{data['output.current']}A*\n"
        f"Temp:     *{data['ups.temperature']}°C*"
    )


def handle_net_command() -> None:
    online, latency = check_internet_latency()
    if online:
        if latency < 20:
            emoji, qualidade = "🟢", "Excelente"
        elif latency < 60:
            emoji, qualidade = "🟡", "Boa"
        else:
            emoji, qualidade = "🟠", "Alta latência"
        send_telegram(
            f"{emoji} *Internet — Online*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Ping:      *{latency:.1f} ms*\n"
            f"Qualidade: *{qualidade}*"
        )
    else:
        send_telegram("🔴 *Internet — Offline*\nSem resposta de 8.8.8.8 e 1.1.1.1")


def telegram_command_loop() -> None:
    offset = None
    log.info("Telegram command loop iniciado")
    while True:
        try:
            params: dict = {"timeout": 30, "allowed_updates": ["message"]}
            if offset is not None:
                params["offset"] = offset
            url = (
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?"
                + urllib.parse.urlencode(params)
            )
            resp = urllib.request.urlopen(url, timeout=35)
            updates = json.loads(resp.read()).get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                text = msg.get("text", "").strip()
                chat_id = str(msg.get("chat", {}).get("id", ""))
                if chat_id != CHAT_ID:
                    continue
                log.info("Comando recebido: %s", text)
                if text == "#nut":
                    handle_nut_command()
                elif text == "#net":
                    handle_net_command()
        except Exception as exc:
            log.warning("Telegram polling erro: %s", exc)
            time.sleep(10)


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("Iniciando monitor Ragtech Easy Pro -> %s", UPS_NAME)

    cmd_thread = threading.Thread(target=telegram_command_loop, daemon=True)
    cmd_thread.start()

    last_status = load_last_status()
    if last_status:
        log.info("Estado anterior carregado: %s", last_status)

    recovery_thread = None
    last_nas_online = None
    nas_check_counter = 0

    while True:
        data = read_ups()
        if data:
            set_cached_ups(data)
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
                last_nas_online = nas_online
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
