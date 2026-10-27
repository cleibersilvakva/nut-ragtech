"""Boot notifications and debounced NAS reachability; no UPS operations."""
import json
import logging
import os
from pathlib import Path
import subprocess
import time
from datetime import datetime
from zoneinfo import ZoneInfo

LOG = logging.getLogger(__name__)
STATE_DIR = Path('/var/lib/ragtech-monitor')
ZONE = ZoneInfo('America/Sao_Paulo')


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    with temp.open('w') as stream:
        json.dump(value, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def read_json(path):
    try:
        value = json.loads(Path(path).read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def boot_info():
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    line = next(x for x in Path('/proc/stat').read_text().splitlines() if x.startswith('btime '))
    return boot_id, int(line.split()[1])


def previous_shutdown():
    try:
        result = subprocess.run(
            ['journalctl', '-b', '-1', '-n', '80', '-o', 'cat', '--no-pager'],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and any(s in result.stdout for s in (
            'Reached target system-reboot.target', 'Rebooting.', 'Shutting down.',
            'Reached target shutdown.target',
        )):
            return 'Desligamento ordenado registrado; motivo não registrado.'
    except (OSError, subprocess.TimeoutExpired):
        pass
    return 'Não determinado: sem registro conclusivo do desligamento anterior.'


def format_time(timestamp):
    return datetime.fromtimestamp(timestamp, ZONE).strftime('%d/%m/%Y às %H:%M:%S')


class BootNotifier:
    def __init__(self, directory=STATE_DIR, info=None, clock=time.time, evidence=previous_shutdown):
        self.directory = Path(directory)
        self.clock = clock
        self.boot_id, self.started = info or boot_info()
        self.path = self.directory / 'boot.json'
        state = read_json(self.path)
        if state.get('boot_id') != self.boot_id:
            marker = read_json(self.directory / 'planned-reboot.json')
            planned = (marker.get('boot_id') == state.get('boot_id')
                       and bool(state.get('boot_id')) and bool(marker.get('reason')))
            self.state = {
                'boot_id': self.boot_id, 'started': self.started, 'sent': False,
                'reason': ('Planejado: ' + marker['reason']) if planned else evidence(),
            }
            atomic_json(self.path, self.state)
        else:
            self.state = state

    def attempt(self, send):
        if self.state.get('sent'):
            return True
        text = (
            '🔄 Raspberry Pi iniciado\n'
            f'Inicialização: {format_time(self.started)} (Brasília)\n'
            f'Aviso: {format_time(self.clock())} (Brasília)\n'
            f'Motivo: {self.state["reason"]}\n'
            'Monitoramento iniciado.'
        )
        if send(text):
            self.state['sent'] = True
            atomic_json(self.path, self.state)
            return True
        return False


def boot_notification_loop(send):
    while True:
        try:
            notifier = BootNotifier()
            while not notifier.attempt(send):
                time.sleep(30)
            return
        except Exception:
            LOG.exception('Falha no aviso de boot; nova tentativa em 30s')
            time.sleep(30)


class NasMonitor:
    def __init__(self, clock=time.monotonic, grace=120, confirmations=3):
        self.clock = clock
        self.ready_at = clock() + grace
        self.confirmations = confirmations
        self.state = None
        self.candidate = None
        self.count = 0

    def observe(self, online):
        if self.clock() < self.ready_at:
            return None
        if online != self.candidate:
            self.candidate, self.count = online, 1
        else:
            self.count += 1
        if self.count < self.confirmations or self.state == online:
            return None
        previous, self.state = self.state, online
        if previous is None:
            return None
        return ('✅ *NAS acessível*\nO Raspberry confirmou que o NAS responde ao ping '
                'após um período de indisponibilidade. Isso não confirma reinício do NAS.'
                if online else
                '🔴 *NAS inacessível pelo Raspberry*\nO NAS não respondeu a três consultas consecutivas. '
                'Isso pode indicar falha de rede ou indisponibilidade do NAS.')


def planned_reboot(reason):
    reason = reason.strip()
    if not reason or len(reason) > 300 or '\n' in reason:
        raise ValueError('Informe um motivo em uma linha, com até 300 caracteres')
    current, _ = boot_info()
    if read_json(STATE_DIR / 'boot.json').get('boot_id') != current:
        raise RuntimeError('Aguarde o monitor registrar o boot atual antes de solicitar o reboot')
    path = STATE_DIR / 'planned-reboot.json'
    atomic_json(path, {'boot_id': current, 'reason': reason})
    try:
        subprocess.run(['systemctl', 'reboot'], check=True)
    except Exception:
        path.unlink(missing_ok=True)
        raise


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3 or sys.argv[1] != '--reboot':
        raise SystemExit('Uso: raspberry_lifecycle.py --reboot "motivo" (como root)')
    planned_reboot(sys.argv[2])
