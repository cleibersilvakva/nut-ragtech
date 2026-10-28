from contextlib import closing
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import hourly_report as report

class HourlyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'db'; self.state=Path(self.temp.name)/'state'
        self.now=datetime(2026,10,28,2,tzinfo=timezone.utc)
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute('CREATE TABLE speedtests(id INTEGER PRIMARY KEY,source TEXT,timestamp TEXT,measured_at TEXT,download_mbps REAL,upload_mbps REAL,ping_ms REAL,jitter_ms REAL,erro TEXT)')
            db.execute('INSERT INTO speedtests VALUES(1,?,?,?,?,?,?,?,?)',('macmini',self.now.isoformat(),self.now.isoformat(),800,500,3,.1,None))
    def test_hourly_dedup_and_next_hour(self):
        sent=[]
        self.assertTrue(report.run(self.db,self.state,sent.append,self.now))
        self.assertFalse(report.run(self.db,self.state,sent.append,self.now+timedelta(minutes=5)))
        self.assertTrue(report.run(self.db,self.state,sent.append,self.now+timedelta(hours=1)))
        self.assertEqual(len(sent),2)
        self.assertIn('27/10 23:00',sent[0]);self.assertIn('800.0 Mbps',sent[0])
    def test_failed_delivery_retries_without_marking_sent(self):
        with self.assertRaises(OSError):report.run(self.db,self.state,MagicMock(side_effect=OSError),self.now)
        self.assertFalse(self.state.exists())
        self.assertTrue(report.run(self.db,self.state,lambda text:None,self.now))
    def test_stale_measurement_has_no_misleading_speed(self):
        text=report.message(self.db,self.now+timedelta(hours=2))
        self.assertIn('Sem medição recente',text);self.assertNotIn('800.0',text)
    def test_failed_measurement_does_not_show_zero(self):
        with closing(sqlite3.connect(self.db)) as db, db:db.execute("UPDATE speedtests SET erro='offline',download_mbps=NULL")
        text=report.message(self.db,self.now)
        self.assertIn('falhou',text);self.assertNotIn('0.0 Mbps',text)
    def test_legacy_raspberry_results_are_excluded(self):
        with closing(sqlite3.connect(self.db)) as db, db:db.execute("UPDATE speedtests SET source='raspberry'")
        self.assertIn('Nenhuma medição',report.message(self.db,self.now))

if __name__=='__main__':unittest.main()
