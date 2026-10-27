"""Targeted patches; preserve unrelated UPS/power operations and credentials."""
import ast
from pathlib import Path


def replace_function(source, name, replacement):
    tree=ast.parse(source)
    node=next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name==name)
    lines=source.splitlines(keepends=True)
    lines[node.lineno-1:node.end_lineno]=[replacement+'\n']
    result=''.join(lines)
    ast.parse(result)
    return result


def ragtech(source):
    source=replace_function(source,'measure_connection', '''def measure_connection() -> dict:
    from macmini_speedtest_client import measure
    return measure()''')
    source=replace_function(source,'_net_worker', '''def _net_worker() -> None:
    try:
        m = measure_connection()
    except Exception:
        send_telegram("⚠️ Medição no Mac mini indisponível. Verifique API e Ethernet; nenhum teste local no Raspberry foi usado.", parse_mode=None)
        return
    loss = m.get('packet_loss_pct')
    loss_text = f"{loss:.1f}%" if loss is not None else "não informado pelo servidor"
    server = m['server']
    text = (
        "📶 Internet de casa — Mac mini\\n"
        "Origem: Mac mini / Ethernet gigabit / ASUS\\n"
        f"Download: {m['download_mbps']:.1f} Mbps\\n"
        f"Upload: {m['upload_mbps']:.1f} Mbps\\n"
        f"Ping: {m['ping_ms']:.1f} ms\\n"
        f"Jitter: {m['jitter_ms']:.2f} ms\\n"
        f"Perda: {loss_text}\\n"
        f"Servidor: {server['name']} — {server['location']}\\n"
        f"Medição (UTC): {m['measured_at']}\\n"
        "Plano informado: 1000 Mbps. Medição recente pode ser reutilizada por até 10 min."
    )
    send_telegram(text, parse_mode=None)''')
    source=source.replace('⏳ *Medindo conexão...* Aguarde ~30s','⏳ *Consultando medição no Mac mini...* Aguarde até 3 minutos')
    return source


def monitor(source):
    return replace_function(source,'_run_speedtest', '''def _run_speedtest():
    from contextlib import closing
    from macmini_speedtest_client import measure
    result, erro = None, None
    try:
        result = measure()
    except Exception:
        erro = "Mac mini indisponível: API, medidor ou Ethernet sem resposta"
        log.warning(erro)
    with closing(sqlite3.connect(cfg.DB_PATH)) as conn, conn:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(speedtests)")}
        for name, definition in [
            ('source', "TEXT DEFAULT 'raspberry'"), ('jitter_ms', 'REAL'),
            ('interface', 'TEXT'), ('server', 'TEXT'), ('measured_at', 'TEXT')
        ]:
            if name not in columns:
                conn.execute(f"ALTER TABLE speedtests ADD COLUMN {name} {definition}")
        conn.execute(
            "INSERT INTO speedtests (timestamp,ping_ms,download_mbps,upload_mbps,erro,source,jitter_ms,interface,server,measured_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (datetime.now().isoformat(), result['ping_ms'] if result else None,
             result['download_mbps'] if result else None, result['upload_mbps'] if result else None,
             erro, 'macmini', result['jitter_ms'] if result else None,
             result['interface'] if result else None, result['server']['name'] if result else None,
             result['measured_at'] if result else None),
        )
    if result:
        log.info("Speedtest Mac mini: download=%.1f Mbps upload=%.1f Mbps ping=%.1f ms",
                 result['download_mbps'],result['upload_mbps'],result['ping_ms'])''')


def report(source):
    source=replace_function(source,'speedtests_dia_anterior', '''def speedtests_dia_anterior() -> list:
    from contextlib import closing
    if not Path(cfg.DB_PATH).exists():
        return []
    ontem = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    with closing(sqlite3.connect(cfg.DB_PATH)) as conn, conn:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(speedtests)")}
        if 'source' not in columns:
            return []
        return conn.execute(
            "SELECT ping_ms,download_mbps,upload_mbps,erro FROM speedtests WHERE date(timestamp)=? AND source='macmini' ORDER BY timestamp", (ontem,)
        ).fetchall()''')
    return source.replace('📶 <b>Speedtest {ontem_str}:</b>', '📶 <b>Speedtest Mac mini / Ethernet — {ontem_str}:</b>')


def patches():
    return [(Path('/opt/ragtech-monitor/ragtech_nut.py'),ragtech),
            (Path('/opt/internet-monitor/monitor.py'),monitor),
            (Path('/opt/internet-monitor/report.py'),report)]
