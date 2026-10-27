#!/usr/bin/env python3
"""Authenticated, asynchronous LAN speed tests on the Mac mini Ethernet."""
from datetime import datetime, timezone
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import math
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / 'config.json').read_text()) if (ROOT / 'config.json').exists() else {}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def ethernet(interface):
    sysfs = Path('/sys/class/net') / interface
    if (sysfs / 'carrier').read_text().strip() != '1':
        raise RuntimeError('ethernet_disconnected')
    speed = int((sysfs / 'speed').read_text())
    if speed < 1000:
        raise RuntimeError('ethernet_below_gigabit')
    addresses = json.loads(subprocess.check_output(['ip', '-j', '-4', 'addr', 'show', 'dev', interface], text=True))
    address = next(x['local'] for x in addresses[0]['addr_info'] if x['family'] == 'inet')
    route = json.loads(subprocess.check_output(['ip', '-j', '-4', 'route', 'get', '1.1.1.1', 'from', address], text=True))[0]
    if route.get('dev') != interface or route.get('gateway') != '192.168.50.1':
        raise RuntimeError('route_not_via_asus_ethernet')
    return dict(interface=interface, source_ip=address, link_mbps=speed, gateway=route['gateway'])


def metric(value):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError('invalid_metric')
    return number


def normalize(raw, link):
    if raw.get('type') != 'result':
        raise ValueError('missing_result')
    actual = raw.get('interface', {})
    if actual.get('internalIp') != link['source_ip'] or actual.get('isVpn') is True:
        raise ValueError('result_not_from_ethernet')
    return dict(origin='macmini', engine='ookla', measured_at=raw['timestamp'], **link,
                download_mbps=metric(raw['download']['bandwidth']) * 8 / 1_000_000,
                upload_mbps=metric(raw['upload']['bandwidth']) * 8 / 1_000_000,
                ping_ms=metric(raw['ping']['latency']), jitter_ms=metric(raw['ping']['jitter']),
                packet_loss_pct=metric(raw['packetLoss']) if raw.get('packetLoss') is not None else None,
                server=dict(id=raw['server']['id'], name=raw['server']['name'], location=raw['server']['location']))


def run_speedtest(config):
    link = ethernet(config['interface'])
    result = subprocess.run([str(ROOT / 'bin/speedtest'), '--accept-license', '--accept-gdpr',
                             '--interface=' + config['interface'], '--format=json', '--progress=no'],
                            capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError('speedtest_failed')
    data = normalize(json.loads(result.stdout), link)
    after = ethernet(config['interface'])
    if after != link:
        raise RuntimeError('ethernet_changed_during_test')
    return data


class Jobs:
    def __init__(self, path, config, runner=run_speedtest):
        self.path, self.config, self.runner = str(path), config, runner
        self.lock = threading.Lock()
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, created REAL, state TEXT, payload TEXT)')
            db.execute("UPDATE jobs SET state='failed', payload=? WHERE state='running'", (json.dumps({'error':'service_restarted'}),))

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, job_id=None):
        with self.connection() as db:
            if job_id:
                row = db.execute('SELECT id,created,state,payload FROM jobs WHERE id=?', (job_id,)).fetchone()
            else:
                row = db.execute('SELECT id,created,state,payload FROM jobs ORDER BY created DESC LIMIT 1').fetchone()
        return dict(id=row[0], created_at=row[1], state=row[2], **json.loads(row[3])) if row else None

    def start(self):
        with self.lock:
            latest = self.get()
            if latest and (latest['state'] == 'running' or
                           (latest['state'] == 'complete' and time.time() - latest['created_at'] < 600)):
                return latest
            if latest and latest['state'] == 'failed' and time.time() - latest['created_at'] < 60:
                return latest
            job_id = str(uuid.uuid4())
            with self.connection() as db:
                db.execute('INSERT INTO jobs VALUES (?,?,?,?)', (job_id, time.time(), 'running', '{}'))
                db.execute('DELETE FROM jobs WHERE created < ?', (time.time() - 90*86400,))
            threading.Thread(target=self.work, args=(job_id,), daemon=True).start()
            return self.get(job_id)

    def work(self, job_id):
        try:
            payload, state = {'result': self.runner(self.config)}, 'complete'
        except Exception as exc:
            code = str(exc)
            known = {'ethernet_disconnected','ethernet_below_gigabit','route_not_via_asus_ethernet',
                     'result_not_from_ethernet','speedtest_failed','ethernet_changed_during_test'}
            payload, state = {'error': code if code in known else 'measurement_failed'}, 'failed'
        with self.connection() as db:
            db.execute('UPDATE jobs SET state=?,payload=? WHERE id=?', (state, json.dumps(payload), job_id))


def handler(jobs, token, allowed):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, status, value):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            self.connection.settimeout(5)
            if self.client_address[0] not in allowed:
                self.respond(403, {'error':'forbidden'})
                return False
            if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                self.respond(401, {'error':'unauthorized'})
                return False
            return True

        def do_GET(self):
            if not self.authorized():
                return
            if self.path == '/health':
                self.respond(200, {'status':'ok','host':socket.gethostname(),'interface':CONFIG.get('interface')})
                return
            if self.path.startswith('/v1/tests/'):
                name = self.path.removeprefix('/v1/tests/')
                job = jobs.get(None if name == 'latest' else name)
                self.respond(200 if job else 404, job or {'error':'not_found'})
                return
            self.respond(404, {'error':'not_found'})

        def do_POST(self):
            if not self.authorized():
                return
            if self.path != '/v1/tests':
                self.respond(404, {'error':'not_found'})
                return
            if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Length', '0') != '0':
                self.respond(400, {'error':'body_not_allowed'})
                return
            job = jobs.start()
            self.respond(202 if job['state']=='running' else 200, job)
    return Handler


if __name__ == '__main__':
    os.umask(0o077)
    state = ROOT / 'data'
    state.mkdir(exist_ok=True)
    token = Path(CONFIG['token_file']).read_text().strip()
    if len(token) < 32:
        raise SystemExit('Token is missing or too short')
    jobs = Jobs(state/'measurements.db', CONFIG)
    ThreadingHTTPServer((CONFIG['bind'],CONFIG['port']), handler(jobs,token,CONFIG['allowed_clients'])).serve_forever()
