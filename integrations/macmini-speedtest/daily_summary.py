"""Previous local day's speed measurements, delivered once after 07:00 Brasilia."""
from contextlib import closing
from datetime import datetime, time, timedelta, timezone
import fcntl
import json
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo
from hourly_report import send
ZONE=ZoneInfo('America/Sao_Paulo')


def summary(db_path, day):
    start=datetime.combine(day,time.min,ZONE).astimezone(timezone.utc)
    end=datetime.combine(day+timedelta(days=1),time.min,ZONE).astimezone(timezone.utc)
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory=sqlite3.Row
        rows=db.execute("SELECT timestamp,download_mbps,upload_mbps,ping_ms,erro FROM speedtests WHERE source='macmini' ORDER BY timestamp").fetchall()
    selected=[]
    for row in rows:
        stamp=datetime.fromisoformat(row['timestamp'])
        if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
        if start<=stamp<end:selected.append((stamp,row))
    good=[row for _,row in selected if row['erro'] is None and all(row[k] is not None for k in ('download_mbps','upload_mbps','ping_ms'))]
    lines=[f"📊 Internet de casa — consolidado {day:%d/%m/%Y}",'Mac mini / Ethernet • horários de Brasília',f'Medições: {len(selected)} | válidas: {len(good)} | falhas: {len(selected)-len(good)}']
    if not selected:lines.append('⚠️ Nenhuma medição registrada nesse dia.')
    if good:
        for field,label,unit in [('download_mbps','↓ Download','Mbps'),('upload_mbps','↑ Upload','Mbps'),('ping_ms','Ping','ms')]:
            values=[row[field] for row in good]
            lines.append(f'{label}: {min(values):.1f} / {sum(values)/len(values):.1f} / {max(values):.1f} {unit} (mín/média/máx)')
    # Hourly averages also cover historical days collected twice per hour.
    hours={}
    for stamp,row in selected:hours.setdefault(stamp.astimezone(ZONE).hour,[]).append(row)
    lines.append('\nPor hora — download / upload (Mbps):')
    for hour,group in sorted(hours.items()):
        valid=[row for row in group if row['erro'] is None and row['download_mbps'] is not None and row['upload_mbps'] is not None]
        if valid:
            down=sum(r['download_mbps'] for r in valid)/len(valid);up=sum(r['upload_mbps'] for r in valid)/len(valid)
            lines.append(f'{hour:02}:00 • ↓ {down:.1f} / ↑ {up:.1f}'+(f' • {len(group)-len(valid)} falha(s)' if len(valid)<len(group) else ''))
        else:lines.append(f'{hour:02}:00 • medição indisponível')
    return '\n'.join(lines)


def run(db_path,state_path,deliver,now=None):
    local=(now or datetime.now(timezone.utc)).astimezone(ZONE)
    if local.hour<7:return False
    day=local.date()-timedelta(days=1)
    path=Path(state_path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        try:state=json.loads(path.read_text())
        except FileNotFoundError:state={}
        if state.get('day')==day.isoformat():return False
        deliver(summary(db_path,day))
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps({'day':day.isoformat(),'sent_at':local.isoformat()}));temp.replace(path)
        return True

if __name__=='__main__':
    import config
    try:
        sent=run(config.DB_PATH,Path(config.DB_PATH).parent/'daily-internet-telegram.json',lambda text:send(text,config))
        print('Consolidado diário: '+('entrega confirmada' if sent else 'aguardando 07h ou já entregue'),flush=True)
    except Exception as error:
        print('Consolidado diário falhou: '+type(error).__name__,flush=True)
        raise SystemExit(1)
