from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import math
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import daily_chart as chart

class ChartTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/'db';self.state=Path(self.tmp.name)/'state.json'
        self.end=datetime(2026,10,29,8,tzinfo=chart.ZONE)
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute('CREATE TABLE speedtests(timestamp TEXT,measured_at TEXT,source TEXT,download_mbps REAL,upload_mbps REAL,ping_ms REAL,erro TEXT)')
        self.add(self.end-timedelta(hours=24),800)
        self.add(self.end-timedelta(hours=23),600)
        self.add(self.end-timedelta(hours=22),None,'failure')
    def add(self,stamp,speed,error=None,source='macmini'):
        utc=stamp.astimezone(timezone.utc).replace(tzinfo=None).isoformat()
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute('INSERT INTO speedtests VALUES(?,?,?,?,?,?,?)',(utc,None,source,speed,500,3,error))
    def test_window_08h_brasilia(self):
        self.assertIsNone(chart.window(datetime(2026,10,29,10,59,tzinfo=timezone.utc)))
        self.assertEqual(chart.window(datetime(2026,10,29,11,tzinfo=timezone.utc)),self.end)
    def test_half_open_24hour_window_and_source(self):
        self.add(self.end,999);self.add(self.end-timedelta(hours=24,seconds=1),999)
        self.add(self.end-timedelta(hours=2),35,source='raspberry')
        data=chart.collect(self.db,self.end)
        self.assertEqual((data['samples'],data['valid'],data['failures']),(3,2,1))
        self.assertEqual(data['stats']['download_mbps']['avg'],700)
        self.assertEqual(data['empty_hours'],22)
        self.assertTrue(math.isnan(data['series']['download_mbps'][2]))
    def test_real_png_is_generated(self):
        from PIL import Image
        target=Path(self.tmp.name)/'chart.png';chart.render(chart.collect(self.db,self.end),target)
        with Image.open(target) as image:self.assertEqual(image.format,'PNG');self.assertGreater(image.width,1000)
    def test_empty_period_renders_without_false_speed(self):
        data=chart.collect(self.db,self.end+timedelta(days=3))
        self.assertEqual(data['valid'],0);self.assertNotIn('0.0 Mbps',chart.caption(data))
        chart.render(data,Path(self.tmp.name)/'empty.png')
    def test_delivery_once_and_not_before_eight(self):
        deliver=MagicMock(return_value=123);renderer=MagicMock()
        self.assertFalse(chart.run(self.db,self.state,deliver,self.end-timedelta(minutes=1),renderer))
        self.assertTrue(chart.run(self.db,self.state,deliver,self.end,renderer))
        self.assertFalse(chart.run(self.db,self.state,deliver,self.end+timedelta(hours=1),renderer))
        deliver.assert_called_once();self.assertEqual(json.loads(self.state.read_text())['message_id'],123)
    def test_retry_next_day_preserves_original_window(self):
        deliver=MagicMock(side_effect=OSError);renderer=MagicMock()
        with self.assertRaises(OSError):chart.run(self.db,self.state,deliver,self.end,renderer)
        self.assertEqual(json.loads(self.state.read_text())['pending_end'],self.end.isoformat())
        deliver=MagicMock(return_value=124)
        chart.run(self.db,self.state,deliver,self.end+timedelta(days=1),renderer)
        self.assertEqual(renderer.call_args.args[0]['end'],self.end)
        self.assertEqual(json.loads(self.state.read_text())['delivered_end'],self.end.isoformat())
    def test_concurrent_runs_only_deliver_once(self):
        deliver=MagicMock(return_value=1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:chart.run(self.db,self.state,deliver,self.end,MagicMock()),range(2)))
        self.assertEqual(sorted(results),[False,True]);deliver.assert_called_once()
    def test_photo_request_and_api_confirmation(self):
        image=Path(self.tmp.name)/'pic.png';image.write_bytes(b'PNG_TEST')
        response=MagicMock();response.read.return_value=b'{"ok":true,"result":{"message_id":42}}'
        response.__enter__.return_value=response
        with patch.object(chart.urllib.request,'urlopen',return_value=response) as http:
            result=chart.send_photo(image,'caption',SimpleNamespace(TELEGRAM_BOT_TOKEN='test',TELEGRAM_CHAT_ID=123))
        self.assertEqual(result,42);self.assertIn(b'PNG_TEST',http.call_args.args[0].data)
        self.assertTrue(http.call_args.args[0].full_url.endswith('/sendPhoto'))

if __name__=='__main__':unittest.main()
