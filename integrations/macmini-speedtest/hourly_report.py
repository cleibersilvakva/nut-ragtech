"""Hourly Telegram report from the existing Mac mini measurements."""
from contextlib import closing
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import sqlite3
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo


def message(db_path, now):
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM speedtests WHERE source='macmini' ORDER BY id DESC LIMIT 1").fetchone()
    header = '📶 Internet de casa — relatório horário\nMac mini / Ethernet\n'
    if row is None:
        return header + '⚠️ Nenhuma medição disponível.'
    stamp = datetime.fromisoformat(row['measured_at'] or row['timestamp'])
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)  # Pi records legacy timestamps in UTC.
    when = stamp.astimezone(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m %H:%M')
    if not 0 <= (now - stamp).total_seconds() <= 3900:
        return header + '⚠️ Sem medição recente; verifique o monitor e o Mac mini.'
    if row['erro'] or any(row[k] is None for k in ('download_mbps', 'upload_mbps', 'ping_ms')):
        return header + '⚠️ Última medição falhou; velocidade indisponível.\nHorário: ' + when + ' (Brasília)'
    return (header + f"↓ Download: {row['download_mbps']:.1f} Mbps\n"
            f"↑ Upload: {row['upload_mbps']:.1f} Mbps\nPing: {row['ping_ms']:.1f} ms\n"
            + (f"Jitter: {row['jitter_ms']:.2f} ms\n" if row['jitter_ms'] is not None else '')
            + f'Medição: {when} (Brasília)')


def send(text, config):
    body = urllib.parse.urlencode({'chat_id': config.TELEGRAM_CHAT_ID, 'text': text}).encode()
    request = urllib.request.Request('https://api.telegram.org/bot' + config.TELEGRAM_BOT_TOKEN + '/sendMessage', data=body)
    with urllib.request.urlopen(request, timeout=15) as response:
        result = json.load(response)
    if result.get('ok') is not True:
        raise RuntimeError('Telegram não confirmou a entrega')


def run(db_path, state_path, deliver, now=None):
    now = now or datetime.now(timezone.utc)
    key = now.astimezone(timezone.utc).strftime('%Y-%m-%dT%H')
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            state = json.loads(state_path.read_text())
        except FileNotFoundError:
            state = {}
        if state.get('hour') == key:
            return False
        deliver(message(db_path, now))
        temp = state_path.with_suffix('.tmp')
        temp.write_text(json.dumps({'hour': key, 'sent_at': now.isoformat()}))
        temp.replace(state_path)
        return True


if __name__ == '__main__':
    import config
    try:
        sent = run(config.DB_PATH, Path(config.DB_PATH).parent/'hourly-telegram.json', lambda text: send(text, config))
        print('Relatório horário: ' + ('entrega confirmada' if sent else 'já entregue nesta hora'), flush=True)
    except Exception as error:
        print('Relatório horário falhou: ' + type(error).__name__ + '; nova tentativa pelo cron', flush=True)
        raise SystemExit(1)
