import unittest
from types import SimpleNamespace
from validation_guard import validate,restore_client

class GuardTests(unittest.TestCase):
    def fake(self,ups='OL',system='running',stop_fails=False,still_active=False,start_fails=False):
        calls=[]
        def run(args,**kwargs):
            calls.append(args)
            if args[0].endswith('upsc'):return SimpleNamespace(returncode=0,stdout=ups)
            if 'is-system-running' in args:return SimpleNamespace(returncode=0,stdout=system)
            if 'stop' in args and stop_fails:raise RuntimeError('stop failed')
            if 'is-active' in args:return SimpleNamespace(returncode=0 if still_active else 3,stdout='active' if still_active else 'inactive')
            return SimpleNamespace(returncode=1 if start_fails and 'start' in args else 0,stdout='')
        return run,calls
    def test_safe_dry_run_restores_client(self):
        run,calls=self.fake();tests=[]
        validate(run=run,test=lambda **kw:tests.append(kw) or True)
        self.assertEqual(tests,[{'real':False,'privsep':True}]);self.assertIn('stop',calls[1]);self.assertIn('start',calls[-1])
    def test_failure_restores_client(self):
        run,calls=self.fake()
        def test(**kw):raise RuntimeError('test failed')
        with self.assertRaises(RuntimeError):validate(run=run,test=test)
        self.assertIn('start',calls[-1])
    def test_critical_ups_does_not_stop_production(self):
        for ups in ['OB','FSD OL','OL LB FSD','']:
            run,calls=self.fake(ups=ups)
            with self.assertRaises(RuntimeError):validate(run=run,test=lambda **_:self.fail())
            self.assertEqual(len(calls),1)
    def test_stop_failure_still_restores(self):
        run,calls=self.fake(stop_fails=True)
        with self.assertRaises(RuntimeError):validate(run=run,test=lambda **_:self.fail())
        self.assertIn('start',calls[-1])
    def test_no_second_client_if_stop_did_not_finish(self):
        run,calls=self.fake(still_active=True)
        with self.assertRaises(RuntimeError):validate(run=run,test=lambda **_:self.fail())
        self.assertIn('start',calls[-1])
    def test_no_restart_during_system_poweroff(self):
        run,calls=self.fake(system='stopping')
        validate(real=True,run=run,test=lambda **_:True)
        self.assertFalse(any('start' in c for c in calls))
    def test_restore_failure_is_reported(self):
        run,calls=self.fake(start_fails=True)
        with self.assertRaisesRegex(RuntimeError,'restore'):restore_client(run)

if __name__=='__main__':unittest.main(verbosity=2)
