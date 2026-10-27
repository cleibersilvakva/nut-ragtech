import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import raspberry_lifecycle as life


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.messages = []

    def notifier(self, boot='a', **kwargs):
        return life.BootNotifier(self.directory, (boot, 1000), clock=lambda: 1100,
                                 evidence=lambda: 'Não determinado', **kwargs)

    def send(self, message):
        self.messages.append(message)
        return True

    def test_first_boot_message_and_timezone(self):
        self.assertTrue(self.notifier().attempt(self.send))
        self.assertIn('Raspberry Pi iniciado', self.messages[0])
        self.assertIn('Brasília', self.messages[0])
        self.assertIn('Não determinado', self.messages[0])

    def test_service_restart_does_not_notify_again(self):
        self.notifier().attempt(self.send)
        self.notifier().attempt(self.send)
        self.assertEqual(len(self.messages), 1)

    def test_new_boot_notifies(self):
        self.notifier().attempt(self.send)
        self.notifier('b').attempt(self.send)
        self.assertEqual(len(self.messages), 2)

    def test_network_failure_retries_after_service_restart(self):
        self.assertFalse(self.notifier().attempt(lambda _: False))
        self.assertTrue(self.notifier().attempt(self.send))
        self.assertEqual(len(self.messages), 1)

    def test_planned_reason_and_stale_marker(self):
        self.notifier().attempt(self.send)
        life.atomic_json(self.directory / 'planned-reboot.json', {'boot_id': 'a', 'reason': 'Atualização do SO'})
        notifier = self.notifier('b')
        self.assertIn('Atualização do SO', notifier.state['reason'])
        notifier.attempt(self.send)
        self.assertEqual(self.notifier('c').state['reason'], 'Não determinado')

    def test_corrupt_state_recovers(self):
        (self.directory / 'boot.json').write_text('broken')
        self.assertTrue(self.notifier().attempt(self.send))

    def test_shutdown_evidence_is_not_a_claim_of_cause(self):
        with patch.object(life.subprocess, 'run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = 'Reached target system-reboot.target'
            self.assertIn('motivo não registrado', life.previous_shutdown())
            run.return_value.stdout = ''
            self.assertIn('Não determinado', life.previous_shutdown())

    def test_startup_failed_ping_then_success_is_silent(self):
        now = [0]
        monitor = life.NasMonitor(clock=lambda: now[0])
        for online in [False, True, False, True]:
            self.assertIsNone(monitor.observe(online))
        now[0] = 121
        for online in [False, True, True, True]:
            self.assertIsNone(monitor.observe(online))

    def test_nas_outage_recovery_and_transient_failure(self):
        monitor = life.NasMonitor(grace=0)
        for _ in range(3):
            self.assertIsNone(monitor.observe(True))
        self.assertIsNone(monitor.observe(False))
        self.assertIsNone(monitor.observe(True))
        self.assertIsNone(monitor.observe(False))
        self.assertIsNone(monitor.observe(False))
        self.assertIn('inacessível', monitor.observe(False))
        self.assertIsNone(monitor.observe(False))
        self.assertIsNone(monitor.observe(True))
        self.assertIsNone(monitor.observe(True))
        self.assertIn('acessível', monitor.observe(True))
        self.assertIsNone(monitor.observe(True))

    def test_offline_initial_baseline_silent(self):
        monitor = life.NasMonitor(grace=0)
        for _ in range(3):
            self.assertIsNone(monitor.observe(False))

    def test_failed_reboot_removes_marker(self):
        life.atomic_json(self.directory / 'boot.json', {'boot_id': 'a'})
        with patch.object(life, 'STATE_DIR', self.directory), patch.object(life, 'boot_info', return_value=('a', 1)), patch.object(life.subprocess, 'run', side_effect=OSError):
            with self.assertRaises(OSError):
                life.planned_reboot('Manutenção')
        self.assertFalse((self.directory / 'planned-reboot.json').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
