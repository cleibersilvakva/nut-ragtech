from pathlib import Path
import tempfile,unittest
import nas_recovery as recovery

class RecoveryTests(unittest.TestCase):
    def sample(self,t,status='OL',battery=90):return dict(at=t,boot_id='pi',status=status,battery=battery)
    def advance(self,policy,start,end,online=False,status='OL',battery=90):
        actions=[]
        for t in range(start,end+1,5):actions.append(policy.step(self.sample(t,status,battery),online,True,t))
        return actions
    def test_no_recovery_without_pending(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state'
            self.assertFalse(recovery.read_state(p)['pending'])
    def test_pending_is_persistent_and_once(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state';recovery.mark_pending('one',p);recovery.mark_pending('two',p)
            self.assertEqual(recovery.read_state(p)['reason'],'one')
    def test_corruption_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state';p.write_text('bad')
            self.assertTrue(recovery.read_state(p)['disabled'])
    def test_stable_power_and_offline_before_clear(self):
        p=recovery.Policy(0,'pi')
        self.assertNotIn('clear',self.advance(p,0,175))
        self.assertEqual(p.step(self.sample(180),False,True,180),'clear')
    def test_no_clear_or_wake_while_nas_online(self):
        p=recovery.Policy(0,'pi');actions=self.advance(p,0,500,online=True)
        self.assertNotIn('clear',actions);self.assertNotIn('wake',actions)
    def test_no_wake_on_battery(self):
        p=recovery.Policy(0,'pi');self.assertEqual(set(self.advance(p,0,400,status='OB')),{'wait'})
    def test_low_battery_does_not_recover(self):
        p=recovery.Policy(0,'pi');self.assertEqual(set(self.advance(p,0,400,battery=79)),{'wait'})
    def test_outage_resets_stability(self):
        p=recovery.Policy(0,'pi');self.advance(p,0,175);p.step(self.sample(180,'OB'),False,True,180)
        self.assertNotIn('clear',self.advance(p,185,360));self.assertEqual(p.step(self.sample(365),False,True,365),'clear')
    def test_stale_or_other_boot_not_actionable(self):
        for sample in [None,self.sample(0),dict(at=100,boot_id='other',status='OL',battery=90)]:
            self.assertEqual(recovery.Policy(0,'pi').step(sample,False,True,100),'wait')
    def test_gap_resets_stability(self):
        p=recovery.Policy(0,'pi');self.advance(p,0,175)
        self.assertEqual(p.step(self.sample(250),False,True,250),'wait')
    def test_gateway_unreachable_never_confirms_shutdown(self):
        p=recovery.Policy(0,'pi')
        for t in range(0,400,5):self.assertEqual(p.step(self.sample(t),False,False,t),'wait')
    def test_timeout_never_requests_wol(self):
        p=recovery.Policy(0,'pi',timeout=50)
        self.assertEqual(p.step(self.sample(50),False,True,50),'timeout')
    def test_wake_only_after_clear(self):
        p=recovery.Policy(0,'pi');self.advance(p,0,180);p.cleared=True
        self.assertEqual(p.step(self.sample(185),False,True,185),'wake')
    def test_wake_retry_limit(self):
        p=recovery.Policy(0,'pi',attempts=3);p.cleared=True;p.last_wake=0
        self.advance(p,0,175)
        self.assertEqual(p.step(self.sample(180),False,True,180),'failed')
    def test_three_responses_confirm_return(self):
        p=recovery.Policy(0,'pi',attempts=1);p.cleared=True;self.advance(p,0,180)
        self.assertEqual(self.advance(p,185,195,online=True)[-1],'complete')
    def test_new_outage_invalidates_prior_clear(self):
        p=recovery.Policy(0,'pi');p.cleared=True
        p.step(self.sample(0,'OB'),False,True,0);self.assertFalse(p.cleared)

if __name__=='__main__':unittest.main(verbosity=2)

class DriverTests(unittest.TestCase):
    def run_case(self,online_mode='after_wake',clear_ok=True,change_at_guard=False,fsd=False):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'state'
            if not fsd:recovery.mark_pending('test',path)
            clock=[0];events=[];reads={}
            boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            def sample():
                at=clock[0];reads[at]=reads.get(at,0)+1
                status='OB' if change_at_guard and reads[at]>1 else 'OL'
                return dict(at=at,boot_id=boot,status=status,battery=90)
            def online():return online_mode=='always' or (online_mode=='after_wake' and 'wake' in events)
            def clear():events.append('clear');return clear_ok
            def wake():events.append('wake')
            def sleep(seconds):clock[0]+=seconds
            ok=recovery.recover(sample,online,lambda:True,clear,wake,lambda text:events.append(text),
                                lambda:fsd,path=path,clock=lambda:clock[0],sleep=sleep,stable_seconds=10,timeout=50)
            return ok,events,recovery.read_state(path)
    def test_complete_cycle(self):
        ok,events,state=self.run_case()
        self.assertTrue(ok);self.assertEqual(events.count('clear'),1);self.assertEqual(events.count('wake'),1)
        self.assertFalse(state['pending'])
    def test_timeout_no_wol_when_nas_stays_on(self):
        ok,events,state=self.run_case(online_mode='always')
        self.assertFalse(ok);self.assertNotIn('wake',events);self.assertNotIn('clear',events);self.assertTrue(state['pending'])
    def test_clear_failure_no_wol(self):
        ok,events,state=self.run_case(clear_ok=False)
        self.assertFalse(ok);self.assertNotIn('wake',events);self.assertTrue(state['pending'])
    def test_immediate_guard_blocks_wol_after_new_outage(self):
        ok,events,state=self.run_case(change_at_guard=True)
        self.assertFalse(ok);self.assertNotIn('wake',events)
    def test_existing_fsd_creates_recovery_state(self):
        ok,events,state=self.run_case(fsd=True)
        self.assertTrue(ok);self.assertIn('wake',events);self.assertFalse(state['pending'])
