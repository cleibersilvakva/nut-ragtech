from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller import Controller,write_json

class Actions:
    def __init__(self):self.online={'boot_id':'macboot'};self.accept=True;self.events=[]
    def status(self):return self.online
    def suspend(self):self.events.append('suspend');return self.accept
    def wake(self):self.events.append('wake')
    def notify(self,text):self.events.append(text)

class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'state.json';self.actions=Actions()
        self.config=dict(enabled=True,pi_boot_id='pi',suspend_battery=40,wake_battery=80,stable_seconds=180)
        self.c=Controller(self.path,self.actions,self.config)
    def sample(self,now,status='OB',battery=40):return dict(at=now,boot_id='pi',status=status,battery=battery)
    def step(self,now,status='OB',battery=40):self.c.step(self.sample(now,status,battery),now)
    def suspend(self):
        for t in (0,5,10):self.step(t)
    def sleeping(self):
        self.suspend();self.actions.online=None;self.step(30)
    def advance(self,start,end,status='OL',battery=100):
        for t in range(start,end+1,5):self.step(t,status,battery)
    def test_no_action_on_mains_or_high_battery(self):
        for t in range(0,100,5):self.step(t,'OL',20)
        for t in range(100,200,5):self.step(t,'OB',41)
        self.assertNotIn('suspend',self.actions.events)
    def test_three_distinct_samples_required(self):
        self.step(0);self.c.step(self.sample(0),1);self.c.step(self.sample(0),2)
        self.assertNotIn('suspend',self.actions.events)
        self.step(5);self.step(10);self.assertEqual(self.actions.events.count('suspend'),1)
    def test_no_duplicate_suspend(self):
        self.suspend();self.actions.online=None
        for t in range(15,200,5):self.step(t)
        self.assertEqual(self.actions.events.count('suspend'),1)
    def test_no_wake_for_manual_offline(self):
        self.actions.online=None
        for t in range(0,400,5):self.step(t,'OL',100)
        self.assertNotIn('wake',self.actions.events)
    def test_stale_sample_or_wrong_boot_never_acts(self):
        for t in (30,40,50):self.c.step(self.sample(0),t)
        s=self.sample(60);s['boot_id']='other';self.c.step(s,60)
        self.assertNotIn('suspend',self.actions.events)
    def test_corrupt_state_disables_actions(self):
        self.path.write_text('broken');self.c=Controller(self.path,self.actions,self.config)
        self.suspend();self.assertEqual(self.c.state['phase'],'disabled')
    def test_restart_preserves_ownership(self):
        self.sleeping();self.c=Controller(self.path,self.actions,self.config)
        self.assertTrue(self.c.state['owned']);self.assertEqual(self.c.state['phase'],'sleeping')
    def test_stable_mains_and_80_required(self):
        self.sleeping()
        for t in range(35,300,5):self.step(t,'OL',79)
        self.assertNotIn('wake',self.actions.events)
        self.advance(300,475,'OL',80)
        self.assertNotIn('wake',self.actions.events)
        self.step(480,'OL',80);self.assertEqual(self.actions.events.count('wake'),1)
    def test_new_outage_resets_stability(self):
        self.sleeping();self.advance(35,195);self.step(200,'OB',100);self.advance(210,380)
        self.assertNotIn('wake',self.actions.events)
        self.step(390,'OL',100);self.assertIn('wake',self.actions.events)
    def test_stale_data_resets_recovery_timer(self):
        self.sleeping();self.advance(35,195);self.c.step(None,200);self.advance(215,390)
        self.assertNotIn('wake',self.actions.events)
    def test_wake_confirmation_clears_ownership(self):
        self.sleeping();self.advance(35,215)
        self.actions.online={'boot_id':'macboot'};self.advance(220,245)
        self.assertFalse(self.c.state['owned']);self.assertTrue(any('Mesmo boot' in x for x in self.actions.events))
    def test_wol_retries_are_bounded(self):
        self.sleeping();self.advance(35,210)
        for t in range(215,600,5):self.step(t,'OL',100)
        self.assertEqual(self.actions.events.count('wake'),3)
    def test_failed_suspend_never_allows_wake(self):
        self.actions.accept=False;self.suspend()
        for t in range(20,400,5):self.step(t,'OL',100)
        self.assertFalse(self.c.state['owned']);self.assertNotIn('wake',self.actions.events)
    def test_gap_between_fresh_samples_restarts_stability(self):
        self.sleeping();self.advance(35,195)
        self.step(250,'OL',100);self.advance(255,420)
        self.assertNotIn('wake',self.actions.events)
        self.advance(425,430);self.assertIn('wake',self.actions.events)
    def test_suspend_retries_bounded_when_remote_rejects(self):
        self.actions.accept=False
        for t in range(0,400,5):self.step(t)
        self.assertEqual(self.actions.events.count('suspend'),3)
        self.assertFalse(self.c.state['owned'])
    def test_already_awake_after_energy_return_needs_no_wol(self):
        self.sleeping();self.actions.online={'boot_id':'macboot'};self.advance(35,215)
        self.assertNotIn('wake',self.actions.events)
        self.assertFalse(self.c.state['owned'])
    def test_bad_battery_is_not_actionable(self):
        for value in [None,'broken',float('nan'),101,-1]:
            sample=self.sample(10);sample['battery']=value
            self.c.step(sample,10)
        self.assertEqual(self.actions.events,[])
    def test_disabled_config_is_inert(self):
        self.config['enabled']=False;self.suspend();self.assertEqual(self.actions.events,[])
    def test_failed_ssh_does_not_claim_suspension(self):
        self.actions.online=None;self.suspend();self.assertFalse(self.c.state['owned'])

if __name__=='__main__':unittest.main(verbosity=2)
