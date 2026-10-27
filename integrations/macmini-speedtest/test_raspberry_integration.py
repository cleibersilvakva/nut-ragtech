import ast
from contextlib import closing
from datetime import datetime,timedelta
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import sys
import patch_raspberry
import macmini_speedtest_client as client


class RaspberryTests(unittest.TestCase):
    def test_real_patches_preserve_ups_and_other_functions(self):
        for path, transform in patch_raspberry.patches():
            source=path.read_text()
            updated=transform(source)
            self.assertEqual(transform(updated),updated)
            old,new=ast.parse(source),ast.parse(updated)
            allowed={'measure_connection','_net_worker','handle_net_command','_run_speedtest','speedtests_dia_anterior','gerar_relatorio'}
            for node in old.body:
                if isinstance(node,ast.FunctionDef) and node.name not in allowed:
                    other=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name==node.name)
                    self.assertEqual(ast.dump(node),ast.dump(other),node.name)

    def load_function(self,path,transform,name,namespace):
        tree=ast.parse(transform(path.read_text()))
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
        module=ast.Module(body=[node],type_ignores=[])
        exec(compile(module,'<isolated-function>','exec'),namespace)
        return namespace[name]

    def test_periodic_records_macmini_source_and_failures(self):
        with tempfile.TemporaryDirectory() as d:
            db=str(Path(d)/'events.db')
            with closing(sqlite3.connect(db)) as conn, conn:
                conn.execute('CREATE TABLE speedtests (id INTEGER PRIMARY KEY,timestamp TEXT,ping_ms REAL,download_mbps REAL,upload_mbps REAL,erro TEXT)')
                conn.execute("INSERT INTO speedtests (timestamp,download_mbps) VALUES ('2026-01-01',35)")
            class Log:
                def warning(self,*args):pass
                def info(self,*args):pass
            ns=dict(sqlite3=sqlite3,cfg=SimpleNamespace(DB_PATH=db),datetime=datetime,log=Log())
            run=self.load_function(Path('/opt/internet-monitor/monitor.py'),patch_raspberry.monitor,'_run_speedtest',ns)
            result=dict(ping_ms=3,download_mbps=800,upload_mbps=500,jitter_ms=.1,interface='enp3s0f0',server={'name':'Test'},measured_at='2026-01-01T00:00:00Z')
            with patch.object(client,'measure',return_value=result):run()
            with patch.object(client,'measure',side_effect=RuntimeError):run()
            with closing(sqlite3.connect(db)) as conn, conn:
                rows=conn.execute('SELECT source,download_mbps,erro FROM speedtests ORDER BY id').fetchall()
            self.assertEqual(rows[0][0],'raspberry')
            self.assertEqual(rows[1],('macmini',800,None))
            self.assertEqual(rows[2][0],'macmini')
            self.assertIsNone(rows[2][1])
            self.assertIsNotNone(rows[2][2])

    def test_daily_report_excludes_legacy_and_accepts_iso_dates(self):
        with tempfile.TemporaryDirectory() as d:
            db=str(Path(d)/'events.db')
            stamp=(datetime.now()-timedelta(days=1)).isoformat()
            with closing(sqlite3.connect(db)) as conn, conn:
                conn.execute('CREATE TABLE speedtests(timestamp TEXT,ping_ms REAL,download_mbps REAL,upload_mbps REAL,erro TEXT,source TEXT)')
                for source,speed in [('raspberry',35),('macmini',800)]:
                    conn.execute('INSERT INTO speedtests VALUES (?,?,?,?,?,?)',(stamp,3,speed,500,None,source))
            ns=dict(Path=Path,sqlite3=sqlite3,cfg=SimpleNamespace(DB_PATH=db),datetime=datetime,timedelta=timedelta)
            run=self.load_function(Path('/opt/internet-monitor/report.py'),patch_raspberry.report,'speedtests_dia_anterior',ns)
            self.assertEqual(run(),[(3,800,500,None)])

    def test_telegram_error_is_not_zero_speed(self):
        sent=[]
        def failed():raise RuntimeError('offline')
        ns=dict(measure_connection=failed,send_telegram=lambda text,**kw:sent.append(text))
        run=self.load_function(Path('/opt/ragtech-monitor/ragtech_nut.py'),patch_raspberry.ragtech,'_net_worker',ns)
        run()
        self.assertIn('indisponível',sent[0])
        self.assertNotIn('0.0 Mbps',sent[0])


if __name__=='__main__':unittest.main(verbosity=2)
