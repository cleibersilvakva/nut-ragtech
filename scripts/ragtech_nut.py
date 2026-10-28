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
import os as _credentials_os
from pathlib import Path as _CredentialsPath
_credentials = json.loads(_CredentialsPath(_credentials_os.environ.get("RAGTECH_CREDENTIALS_FILE", "/etc/ragtech-monitor/credentials.json")).read_text())
from nas_recovery import record_critical, recover
import sys as _power_sys
_power_sys.path.insert(0, "/opt/macmini-ups-power")
from daemon import publish_sample
from raspberry_lifecycle import NasMonitor, boot_notification_loop
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
NUT_PASS = _credentials['nut_pass']

BOT_TOKEN = _credentials['bot_token']
CHAT_ID = _credentials['chat_id']
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
        low_battery = battery_pct <= 83

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


def send_telegram(text: str, parse_mode="Markdown") -> bool:
    params = {"chat_id": CHAT_ID, "text": text}
    if parse_mode:
        params["parse_mode"] = parse_mode
    payload = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(
            urllib.request.Request(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data=payload,
            ), timeout=10,
        ) as response:
            return bool(json.loads(response.read()).get("ok"))
    except Exception:
        # Do not log URLs or exceptions containing the Telegram token.
        log.warning("Telegram falhou; mensagem nao confirmada")
        return False


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


def measure_connection() -> dict:
    from macmini_speedtest_client import measure
    return measure()


def send_wol() -> None:
    from wol_transport import send_magic
    receipt = send_magic(NAS_MAC, interface="eth0")
    log.info("WOL aceito pela interface %s origem %s: %s pacotes para %s; aguardando NAS",
             receipt["interface"], receipt["source"], receipt["packets"], NAS_MAC)


def clear_fsd() -> bool:
    def status():
        result = subprocess.run(["upsc", UPS_NAME, "ups.status"],capture_output=True,text=True,timeout=5)
        return result.stdout.split() if result.returncode == 0 else []
    current = status()
    if "OL" in current and "FSD" not in current:
        return True
    try:
        for service in ["nut-monitor","nut-server","nut-driver@ragtech"]:
            subprocess.run(["systemctl","stop",service],check=True,capture_output=True,timeout=20)
        for service in ["nut-driver@ragtech","nut-server","nut-monitor"]:
            subprocess.run(["systemctl","start",service],check=True,capture_output=True,timeout=20)
            time.sleep(2)
        for _ in range(10):
            current = status()
            if "OL" in current and "FSD" not in current:
                return True
            time.sleep(1)
    except Exception:
        log.exception("Falha ao recuperar pilha NUT")
    return False


def power_restored_sequence() -> None:
    with _recovery_lock:
        from pathlib import Path
        def sample():
            try:
                return json.loads(Path("/run/ragtech-power/sample.json").read_text())
            except (OSError,ValueError):
                return None
        def gateway():
            return subprocess.run(["ping","-c","1","-W","1","192.168.50.1"],capture_output=True).returncode == 0
        def fsd():
            result = subprocess.run(["upsc",UPS_NAME,"ups.status"],capture_output=True,text=True,timeout=5)
            return result.returncode == 0 and "FSD" in result.stdout.split()
        recover(sample,ping_nas,gateway,clear_fsd,send_wol,
                lambda text: send_telegram(text,parse_mode=None),fsd)


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


def _net_worker() -> None:
    try:
        m = measure_connection()
    except Exception:
        send_telegram("⚠️ Medição no Mac mini indisponível. Verifique API e Ethernet; nenhum teste local no Raspberry foi usado.", parse_mode=None)
        return
    loss = m.get('packet_loss_pct')
    loss_text = f"{loss:.1f}%" if loss is not None else "não informado pelo servidor"
    server = m['server']
    text = (
        "📶 Internet de casa — Mac mini\n"
        "Origem: Mac mini / Ethernet gigabit / ASUS\n"
        f"Download: {m['download_mbps']:.1f} Mbps\n"
        f"Upload: {m['upload_mbps']:.1f} Mbps\n"
        f"Ping: {m['ping_ms']:.1f} ms\n"
        f"Jitter: {m['jitter_ms']:.2f} ms\n"
        f"Perda: {loss_text}\n"
        f"Servidor: {server['name']} — {server['location']}\n"
        f"Medição (UTC): {m['measured_at']}\n"
        "Plano informado: 1000 Mbps. Medição recente pode ser reutilizada por até 10 min."
    )
    send_telegram(text, parse_mode=None)


def handle_net_command() -> None:
    send_telegram("⏳ *Consultando medição no Mac mini...* Aguarde até 3 minutos")
    threading.Thread(target=_net_worker, daemon=True).start()


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

    threading.Thread(
        target=boot_notification_loop,
        args=(lambda text: send_telegram(text, parse_mode=None),), daemon=True,
    ).start()

    cmd_thread = threading.Thread(target=telegram_command_loop, daemon=True)
    cmd_thread.start()

    last_status = load_last_status()
    if last_status:
        log.info("Estado anterior carregado: %s", last_status)

    recovery_thread = threading.Thread(target=power_restored_sequence, daemon=True)
    recovery_thread.start()
    nas_monitor = NasMonitor()
    nas_check_counter = 0

    while True:
        data = read_ups()
        if data:
            set_cached_ups(data)
            publish_sample(data)
            record_critical(data)
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
            message = nas_monitor.observe(ping_nas())
            if message:
                log.info("Mudanca confirmada na acessibilidade do NAS")
                send_telegram(message)

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
