#!/usr/bin/env python3
"""
NUT notifycmd — Telegram para ONBATT e LOWBATT.

ONLINE e WOL sao tratados por ragtech_nut.py (sempre em execucao).

Instalar em: /etc/nut/notifycmd.py
Permissoes: chmod 750, chown root:nut
"""
import sys, subprocess, urllib.request, urllib.parse, syslog

BOT_TOKEN = "CHANGE_ME_TELEGRAM_BOT_TOKEN"
CHAT_ID   = "CHANGE_ME_TELEGRAM_CHAT_ID"


def get_battery():
    try:
        r = subprocess.run(["upsc", "ragtech@127.0.0.1", "battery.charge"],
                           capture_output=True, text=True, timeout=5)
        return int(float(r.stdout.strip()))
    except:
        return None


def send(text):
    payload = urllib.parse.urlencode({
        "chat_id":    CHAT_ID,
        "text":       text,
        "parse_mode": "Markdown",
    }).encode()
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                data=payload,
            ),
            timeout=10,
        )
    except Exception as e:
        syslog.syslog(syslog.LOG_ERR, f"notifycmd telegram falhou: {e}")


evento  = " ".join(sys.argv[1:]).upper()
bateria = get_battery()
bat_str = f"\nBateria: *{bateria}%*" if bateria is not None else ""

if "ON BATTERY" in evento or "ONBATT" in evento:
    send(f"🔴 *Nobreak na bateria*\nA energia da rede foi interrompida.{bat_str}")

elif "LOW BATTERY" in evento or "LOWBATT" in evento:
    send(f"⚠️ *Bateria crítica!*\nNível muito baixo atingido.{bat_str}\nO desligamento do NAS deve ser iniciado em breve.")

# ONLINE e WOL: tratados por ragtech_nut.py via deteccao OB→OL no hardware
