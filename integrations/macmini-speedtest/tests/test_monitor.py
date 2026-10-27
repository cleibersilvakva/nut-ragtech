import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server


class MonitorTests(unittest.TestCase):
    def raw(self):
        return dict(type='result', timestamp='2026-10-27T00:00:00Z', interface={'internalIp':'192.168.50.9'},
                    download={'bandwidth':125000000}, upload={'bandwidth':62500000},
                    ping={'latency':4,'jitter':0.5}, packetLoss=0,
                    server={'id':1,'name':'server','location':'Brasilia'})

    def link(self):
        return dict(source_ip='192.168.50.9',interface='enp3s0f0',link_mbps=1000,gateway='192.168.50.1')

    def test_units_and_origin(self):
        result=server.normalize(self.raw(),self.link())
        self.assertEqual(result['download_mbps'],1000)
        self.assertEqual(result['upload_mbps'],500)
        self.assertEqual(result['origin'],'macmini')

    def test_wifi_and_vpn_rejected(self):
        for interface in [{'internalIp':'192.168.50.20'}, {'internalIp':'192.168.50.9','isVpn':True}]:
            raw=self.raw(); raw['interface']=interface
            with self.assertRaises(ValueError): server.normalize(raw,self.link())

    def test_missing_packet_loss_is_not_zero(self):
        raw=self.raw();raw.pop('packetLoss')
        self.assertIsNone(server.normalize(raw,self.link())['packet_loss_pct'])

    def test_bad_metric_rejected(self):
        raw=self.raw(); raw['download']['bandwidth']=float('nan')
        with self.assertRaises(ValueError): server.normalize(raw,self.link())

    def test_disconnected_or_slow_ethernet_refuses_measurement(self):
        with tempfile.TemporaryDirectory() as d:
            interface=Path(d)/'enp3s0f0';interface.mkdir()
            (interface/'carrier').write_text('0')
            (interface/'speed').write_text('1000')
            with patch.object(server,'Path',return_value=Path(d)):
                with self.assertRaisesRegex(RuntimeError,'disconnected'):
                    server.ethernet('enp3s0f0')
                (interface/'carrier').write_text('1')
                (interface/'speed').write_text('100')
                with self.assertRaisesRegex(RuntimeError,'below_gigabit'):
                    server.ethernet('enp3s0f0')

    def test_job_concurrency_cache_and_history(self):
        with tempfile.TemporaryDirectory() as d:
            release=threading.Event();count=[]
            def runner(config):
                count.append(1);release.wait(3);return {'download_mbps':10}
            jobs=server.Jobs(Path(d)/'jobs.db',{},runner)
            first=jobs.start();second=jobs.start()
            self.assertEqual(first['id'],second['id'])
            release.set()
            for _ in range(100):
                if jobs.get()['state']=='complete':break
                time.sleep(.01)
            self.assertEqual(jobs.start()['id'],first['id'])
            self.assertEqual(len(count),1)
            self.assertEqual(jobs.get(first['id'])['result']['download_mbps'],10)

    def test_failure_is_recorded_without_secrets(self):
        with tempfile.TemporaryDirectory() as d:
            def runner(_):raise RuntimeError('secret-token-here')
            jobs=server.Jobs(Path(d)/'j.db',{},runner)
            jobs.start()
            for _ in range(100):
                if jobs.get()['state']=='failed':break
                time.sleep(.01)
            self.assertEqual(jobs.get()['error'],'measurement_failed')

    def test_api_auth_and_paths(self):
        with tempfile.TemporaryDirectory() as d:
            jobs=server.Jobs(Path(d)/'j.db',{},lambda _: {})
            http=server.ThreadingHTTPServer(('127.0.0.1',0),server.handler(jobs,'a'*40,['127.0.0.1']))
            threading.Thread(target=http.serve_forever,daemon=True).start()
            self.addCleanup(http.server_close); self.addCleanup(http.shutdown)
            base=f'http://127.0.0.1:{http.server_port}'
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                opener.open(base+'/health')
            self.assertEqual(ctx.exception.code,401)
            req=urllib.request.Request(base+'/health',headers={'Authorization':'Bearer '+'a'*40})
            self.assertEqual(json.load(opener.open(req))['status'],'ok')
            req=urllib.request.Request(base+'/v1/tests/invalid',headers={'Authorization':'Bearer '+'a'*40})
            with self.assertRaises(urllib.error.HTTPError) as ctx: opener.open(req)
            self.assertEqual(ctx.exception.code,404)

    def test_restart_marks_running_job_failed(self):
        with tempfile.TemporaryDirectory() as d:
            jobs=server.Jobs(Path(d)/'j.db',{})
            with jobs.connection() as db:db.execute('INSERT INTO jobs VALUES (?,?,?,?)',('old',time.time(),'running','{}'))
            jobs=server.Jobs(Path(d)/'j.db',{})
            self.assertEqual(jobs.get('old')['error'],'service_restarted')


if __name__=='__main__':unittest.main(verbosity=2)
