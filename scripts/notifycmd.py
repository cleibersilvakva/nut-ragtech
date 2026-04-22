#!/usr/bin/env python3
"""
NUT notifycmd — Telegram + Wake-on-LAN

Chamado pelo upsmon nos eventos ONBATT, ONLINE, LOWBATT.
Instalar em: /etc/nut/notifycmd.py
Permissões: chmod 750, chown root:nut
"""
import sys, subprocess, urllib.request, urllib.parse, syslog, time

BOT_TOKEN = "CHANGE_ME_TELEGRAM_BOT_TOKEN"
CHAT_ID   = "CHANGE_ME_TELEGRAM_CHAT_ID"

NAS_MAC   = "6c:1f:f7:a8:b1:0d"   # MAC do NAS (Ugreen DH4300 Plus)


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


def wake_nas():
    # Envia magic packet 3x para garantia
    for _ in range(3):
        subprocess.run(["wakeonlan", NAS_MAC], capture_output=True)
        time.sleep(2)
    syslog.syslog(syslog.LOG_INFO, f"notifycmd: WOL enviado para {NAS_MAC}")


evento  = " ".join(sys.argv[1:]).upper()
bateria = get_battery()
bat_str = f"\nBateria: *{bateria}%*" if bateria is not None else ""

if "ON BATTERY" in evento or "ONBATT" in evento:
    send(f"🔴 *Nobreak na bateria*\nA energia da rede foi interrompida.{bat_str}")

elif "ON LINE" in evento or "ONLINE" in evento:
    send(f"✅ *Energia voltou*\nNobreak retornou à rede elétrica.{bat_str}\nEnviando WOL para ligar o NAS...")
    time.sleep(5)
    wake_nas()

elif "LOW BATTERY" in evento or "LOWBATT" in evento:
    send(f"⚠️ *Bateria crítica!*\nNível muito baixo atingido.{bat_str}\nO desligamento do NAS deve ser iniciado em breve.")
