from contextlib import closing
from datetime import datetime,timezone,date,timedelta
import sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock
import daily_summary as daily

class DailyTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.db=Path(self.tmp.name)/'db';self.state=Path(self.tmp.name)/'state'
  with closing(sqlite3.connect(self.db)) as c, c:
   c.execute('CREATE TABLE speedtests(timestamp TEXT,source TEXT,download_mbps REAL,upload_mbps REAL,ping_ms REAL,erro TEXT)')
   for stamp,source,speed,error in [('2026-10-27T02:59:59','macmini',999,None),('2026-10-27T03:00:00','macmini',800,None),('2026-10-28T02:59:59','macmini',600,None),('2026-10-28T03:00:00','macmini',999,None),('2026-10-27T12:00:00','raspberry',35,None),('2026-10-27T13:00:00','macmini',None,'offline')]:
    c.execute('INSERT INTO speedtests VALUES(?,?,?,?,?,?)',(stamp,source,speed,500,3,error))
 def test_local_day_boundaries_and_legacy_exclusion(self):
  text=daily.summary(self.db,date(2026,10,27));self.assertIn('Medições: 3 | válidas: 2 | falhas: 1',text);self.assertIn('700.0',text);self.assertNotIn('999',text);self.assertIn('23:00',text)
 def test_seven_brasilia_and_once_daily(self):
  sent=[];before=datetime(2026,10,28,9,59,tzinfo=timezone.utc)
  self.assertFalse(daily.run(self.db,self.state,sent.append,before));self.assertFalse(self.state.exists())
  self.assertTrue(daily.run(self.db,self.state,sent.append,before+timedelta(minutes=1)))
  self.assertFalse(daily.run(self.db,self.state,sent.append,before+timedelta(hours=1)))
  self.assertEqual(len(sent),1)
 def test_failed_delivery_is_retried(self):
  now=datetime(2026,10,28,10,tzinfo=timezone.utc)
  with self.assertRaises(OSError):daily.run(self.db,self.state,MagicMock(side_effect=OSError),now)
  self.assertFalse(self.state.exists());self.assertTrue(daily.run(self.db,self.state,lambda text:None,now))
 def test_empty_day_is_explicit(self):self.assertIn('Nenhuma medição',daily.summary(self.db,date(2026,1,1)))
if __name__=='__main__':unittest.main()
