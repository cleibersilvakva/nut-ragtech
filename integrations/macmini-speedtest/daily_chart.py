"""One 24-hour internet chart per day, ending 08:00 America/Sao_Paulo."""
from contextlib import closing
from datetime import datetime, time, timedelta, timezone
import fcntl
import json
import math
from pathlib import Path
import secrets
import sqlite3
import urllib.request
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('America/Sao_Paulo')


def parse_stamp(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp


def window(now):
    local = now.astimezone(ZONE)
    if local.hour < 8:
        return None
    return datetime.combine(local.date(), time(8), ZONE)


def collect(db_path, end):
    start = end - timedelta(hours=24)
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT timestamp,measured_at,download_mbps,upload_mbps,ping_ms,erro FROM speedtests WHERE source='macmini' AND julianday(COALESCE(measured_at,timestamp)) >= julianday(?) AND julianday(COALESCE(measured_at,timestamp)) < julianday(?) ORDER BY timestamp", (start.isoformat(), end.isoformat())).fetchall()
    slots = [[] for _ in range(24)]
    failures = 0
    valid = []
    for row in rows:
        stamp = parse_stamp(row['measured_at'] or row['timestamp'])
        index = int((stamp - start).total_seconds() // 3600)
        if not 0 <= index < 24:
            continue
        good = row['erro'] is None and all(isinstance(row[k], (int, float)) and math.isfinite(row[k]) and row[k] >= 0 for k in ('download_mbps', 'upload_mbps', 'ping_ms'))
        if good:
            slots[index].append(dict(row)); valid.append(dict(row))
        else:
            failures += 1
    series = {key: [sum(row[key] for row in group) / len(group) if group else math.nan for group in slots] for key in ('download_mbps', 'upload_mbps', 'ping_ms')}
    stats = {key: {'min': min(row[key] for row in valid), 'avg': sum(row[key] for row in valid) / len(valid), 'max': max(row[key] for row in valid)} for key in series} if valid else {}
    return dict(start=start, end=end, series=series, stats=stats, samples=len(rows), valid=len(valid), failures=failures, empty_hours=sum(not group for group in slots))


def caption(data):
    lines = ['Internet de casa — últimas 24 horas', f"{data['start']:%d/%m %H:%M} até {data['end']:%d/%m %H:%M} (Brasília)", 'Mac mini / Ethernet', f"Medições: {data['samples']} | válidas: {data['valid']} | falhas: {data['failures']}", f"Horas sem medição válida: {data['empty_hours']}/24"]
    for key, label, unit in [('download_mbps', 'Download', 'Mbps'), ('upload_mbps', 'Upload', 'Mbps'), ('ping_ms', 'Ping', 'ms')]:
        if key in data['stats']:
            s = data['stats'][key]
            lines.append(f"{label}: {s['min']:.1f} / {s['avg']:.1f} / {s['max']:.1f} {unit} (mín/média/máx)")
    if not data['valid']:
        lines.append('Sem medições válidas; lacunas não significam velocidade zero.')
    return '\n'.join(lines)


def render(data, destination):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as dates
    times = [data['start'] + timedelta(hours=index, minutes=30) for index in range(24)]
    with plt.rc_context({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False}):
        fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
        axes[0].plot(times, data['series']['download_mbps'], color='#1769aa', label='Download', marker='o', markersize=4)
        axes[0].plot(times, data['series']['upload_mbps'], color='#00897b', label='Upload', marker='o', markersize=4)
        axes[0].set_ylabel('Velocidade (Mbps)'); axes[0].legend(loc='upper left')
        axes[1].plot(times, data['series']['ping_ms'], color='#a4570b', marker='o', markersize=4, label='Ping')
        axes[1].set_ylabel('Latência (ms)')
        for ax in axes:
            ax.set_ylim(bottom=0); ax.grid(alpha=.2)
            ax.set_xlim(data['start'], data['end'])
            if not data['valid']:
                ax.text(.5, .5, 'Sem medições válidas no período', transform=ax.transAxes, ha='center')
        axes[1].xaxis.set_major_locator(dates.HourLocator(interval=3, tz=ZONE))
        axes[1].xaxis.set_major_formatter(dates.DateFormatter('%d/%m\n%H:%M', tz=ZONE))
        fig.suptitle('Internet de casa • últimas 24 horas\n' + f"{data['start']:%d/%m %H:%M} → {data['end']:%d/%m %H:%M} (Brasília)", fontsize=15)
        fig.text(.06, .025, f"Mac mini / Ethernet • {data['valid']} medições válidas • {data['failures']} falhas • {data['empty_hours']} horas sem dados válidos\nCada ponto é a média da faixa horária; lacunas representam dados ausentes ou falhas.", fontsize=9)
        fig.tight_layout(rect=(0, .09, 1, .90))
        try:
            fig.savefig(destination, dpi=150, format='png')
        finally:
            plt.close(fig)


def send_photo(path, text, config):
    boundary = 'InternetReport' + secrets.token_hex(16)
    chunks = []
    for name, value in [('chat_id', str(config.TELEGRAM_CHAT_ID)), ('caption', text)]:
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="internet-24h.png"\r\nContent-Type: image/png\r\n\r\n'.encode())
    chunks.extend([Path(path).read_bytes(), f'\r\n--{boundary}--\r\n'.encode()])
    request = urllib.request.Request('https://api.telegram.org/bot' + config.TELEGRAM_BOT_TOKEN + '/sendPhoto', data=b''.join(chunks), headers={'Content-Type': 'multipart/form-data; boundary=' + boundary})
    with urllib.request.urlopen(request, timeout=40) as response:
        result = json.load(response)
    if result.get('ok') is not True:
        raise RuntimeError('Telegram não confirmou a foto')
    return result.get('result', {}).get('message_id')


def save(path, state):
    temp = path.with_suffix('.tmp'); temp.write_text(json.dumps(state)); temp.replace(path)


def run(db_path, state_path, deliver, now=None, renderer=render):
    now = now or datetime.now(timezone.utc)
    path = Path(state_path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            state = json.loads(path.read_text())
        except FileNotFoundError:
            state = {}
        # A failed delivery retains its exact window, including across midnight.
        end = parse_stamp(state['pending_end']) if state.get('pending_end') else window(now)
        if end is None or state.get('delivered_end') == end.isoformat():
            return False
        state['pending_end'] = end.isoformat(); save(path, state)
        data = collect(db_path, end)
        image = path.parent / ('internet-24h-' + end.strftime('%Y%m%d') + '.png')
        renderer(data, image)
        receipt = deliver(image, caption(data))
        save(path, {'delivered_end': end.isoformat(), 'sent_at': now.isoformat(), 'message_id': receipt})
        for old in path.parent.glob('internet-24h-*.png'):
            if old != image and now.timestamp() - old.stat().st_mtime > 30 * 86400:
                old.unlink()
        return True


if __name__ == '__main__':
    import config
    try:
        sent = run(config.DB_PATH, Path(config.DB_PATH).parent / 'daily-chart-telegram.json', lambda path, text: send_photo(path, text, config))
        print('Gráfico diário: ' + ('entrega confirmada' if sent else 'aguardando 08h ou já entregue'), flush=True)
    except Exception as error:
        # Never log Telegram URLs/tokens from exceptions.
        print('Gráfico diário falhou: ' + type(error).__name__ + '; nova tentativa preserva período', flush=True)
        raise SystemExit(1)
