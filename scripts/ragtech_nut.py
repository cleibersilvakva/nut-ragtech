#!/usr/bin/env python3
"""
Ragtech Easy Pro — NUT bridge daemon.

Le o nobreak via protocolo binario proprietario (USB serial, 2400 baud)
e atualiza o NUT em tempo real via upsrw (dummy-ups driver).

Instalar em: /opt/ragtech-monitor/ragtech_nut.py
"""
import serial
import subprocess
import time
import logging
import sys

PORT      = "/dev/ttyACM0"
CMD       = bytes.fromhex("AA0400801E9E")
POLL_SEC  = 5
UPS_NAME  = "ragtech@127.0.0.1"
NUT_USER  = "admin"
NUT_PASS  = "CHANGE_ME_ADMIN"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


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


def main() -> None:
    log.info("Iniciando monitor Ragtech Easy Pro -> %s", UPS_NAME)
    last_status = None

    while True:
        data = read_ups()
        if data:
            push_to_nut(data)
            if data["ups.status"] != last_status:
                log.info(
                    "Status: %s | Bateria: %s%% | Entrada: %sV | Carga: %s%%",
                    data["ups.status"],
                    data["battery.charge"],
                    data["input.voltage"],
                    data["ups.load"],
                )
                last_status = data["ups.status"]
        else:
            log.warning("Falha na leitura, tentando em %ss...", POLL_SEC)

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
