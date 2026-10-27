#!/usr/bin/env python3
"""Daily Raspberry resource report; APT refresh only, no package installation."""
import argparse
from datetime import datetime
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('America/Sao_Paulo')
STATE = Path('/var/lib/ragtech-monitor')
ENV = {**os.environ, 'LC_ALL': 'C'}


def memory_info(text):
    values = {}
    for line in text.splitlines():
        name, value = line.split(':', 1)
        values[name] = int(value.split()[0]) * 1024
    return values


def cpu_counters(text):
    numbers = [int(x) for x in text.splitlines()[0].split()[1:9]]
    return sum(numbers), numbers[3] + numbers[4]


def cpu_percent(before, after):
    total = after[0] - before[0]
    return max(0, min(100, 100 * (1 - (after[1] - before[1]) / total))) if total > 0 else 0


def packages_from_output(text):
    packages = []
    for line in text.splitlines():
        if '[upgradable from:' in line and '/' in line:
            pieces = line.split()
            if len(pieces) >= 3:
                packages.append((pieces[0].split('/')[0], pieces[1]))
    return sorted(set(packages))


def updates(refresh=True):
    fresh = False
    if refresh:
        try:
            result = subprocess.run(
                ['apt-get', '-o', 'APT::Update::Error-Mode=any', '-o', 'Acquire::Retries=1',
                 '-o', 'Acquire::http::Timeout=20', '-o', 'Acquire::https::Timeout=20', 'update'],
                capture_output=True, text=True, timeout=180, env=ENV,
            )
            fresh = result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        result = subprocess.run(['apt', 'list', '--upgradable'], capture_output=True,
                                text=True, timeout=45, env=ENV)
        if result.returncode:
            return None, fresh
        return packages_from_output(result.stdout), fresh
    except (OSError, subprocess.TimeoutExpired):
        return None, fresh


def size(value):
    return f'{value / 1024**2:.0f} MiB'


def build_report(data):
    mem = data['memory']
    used = mem['MemTotal'] - mem['MemAvailable']
    disk = data['disk']
    uptime = int(data['uptime'])
    lines = [
        '📊 Relatório diário do Raspberry Pi',
        f"{data['host']} — {data['date'].strftime('%d/%m/%Y %H:%M')} (Brasília)",
        '',
        f"CPU: {data['cpu']:.1f}% | carga: {data['load']}",
        f"Memória: {size(used)} / {size(mem['MemTotal'])} ({100 * used / mem['MemTotal']:.0f}%)",
        f"Disponível: {size(mem['MemAvailable'])}",
        f"Swap: {size(mem['SwapTotal'] - mem['SwapFree'])} / {size(mem['SwapTotal'])}",
        f"Disco /: {disk.used / 1024**3:.1f} / {disk.total / 1024**3:.1f} GiB ({100 * disk.used / disk.total:.0f}%)",
        f"Livre: {disk.free / 1024**3:.1f} GiB",
        f"Temperatura: {data['temperature']:.1f} °C" if data['temperature'] is not None else 'Temperatura: leitura indisponível',
        f'Uptime: {uptime // 86400}d {(uptime % 86400) // 3600}h {(uptime % 3600) // 60}min',
        '', '📦 Atualizações de software (APT)',
    ]
    packages = data['packages']
    if packages is None:
        lines.append('Consulta indisponível; não foi possível determinar atualizações.')
    else:
        lines.append(f'{len(packages)} pacote(s) com atualização disponível.' if packages else 'Nenhuma atualização disponível nos índices consultados.')
        for name, version in packages[:12]:
            lines.append(f'• {name}: {version}')
        if len(packages) > 12:
            lines.append(f'… e mais {len(packages) - 12} pacote(s).')
    lines.append('Índices atualizados nesta consulta.' if data['fresh'] else '⚠️ Índices não atualizados nesta consulta; resultado pode estar desatualizado.')
    lines.append('Instalação de pacotes não é automática.')
    if data['reboot_required']:
        lines.append('⚠️ O sistema sinaliza necessidade de reinicialização.')
    return '\n'.join(lines)


def collect(refresh=True):
    before = cpu_counters(Path('/proc/stat').read_text())
    time.sleep(1)
    after = cpu_counters(Path('/proc/stat').read_text())
    try:
        temperature = float(Path('/sys/class/thermal/thermal_zone0/temp').read_text()) / 1000
    except (OSError, ValueError):
        temperature = None
    packages, fresh = updates(refresh)
    return dict(host=socket.gethostname(), date=datetime.now(ZONE), cpu=cpu_percent(before, after),
                memory=memory_info(Path('/proc/meminfo').read_text()), disk=shutil.disk_usage('/'),
                load=' / '.join(f'{x:.2f}' for x in os.getloadavg()), temperature=temperature,
                uptime=float(Path('/proc/uptime').read_text().split()[0]), packages=packages,
                fresh=fresh, reboot_required=Path('/var/run/reboot-required').exists())


def send_report(text):
    # Reuse credentials on the Pi without copying them to this script or Git.
    path = Path('/opt/ragtech-monitor/ragtech_nut.py')
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location('ragtech_report_sender', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.send_telegram(text, parse_mode=None)


def run_once(state_dir=STATE, now=None, collector=collect, sender=send_report):
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    today = (now or datetime.now(ZONE)).date().isoformat()
    with (state_dir / 'daily-report.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        marker = state_dir / 'daily-report-date'
        if marker.exists() and marker.read_text().strip() == today:
            print('Relatório de hoje já confirmado; envio ignorado.')
            return True
        report = build_report(collector())
        if not sender(report):
            print('Envio não confirmado; relatório permanece pendente.', file=sys.stderr)
            return False
        temp = marker.with_suffix('.tmp')
        with temp.open('w') as stream:
            stream.write(today)
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(marker)
        print('Relatório diário confirmado pelo Telegram.')
        return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Exibe relatório sem envio e sem atualizar índices APT')
    args = parser.parse_args()
    if args.dry_run:
        print(build_report(collect(refresh=False)))
    else:
        raise SystemExit(0 if run_once() else 1)
