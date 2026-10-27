from datetime import datetime
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import raspberry_daily_report as report


class DailyReportTests(unittest.TestCase):
    def data(self):
        return dict(host='raspberrypi', date=datetime(2026, 10, 27, 8, tzinfo=report.ZONE),
                    cpu=2.1, load='0.1 / 0.2 / 0.3', memory=dict(MemTotal=1000000000, MemAvailable=700000000,
                    SwapTotal=100000000, SwapFree=100000000), disk=SimpleNamespace(total=8*1024**3, used=5*1024**3, free=3*1024**3),
                    temperature=63.4, uptime=90000, packages=[('linux-image', '1.2')], fresh=True, reboot_required=False)

    def test_cpu_and_memory_parsing(self):
        self.assertEqual(report.cpu_counters('cpu 1 2 3 4 5 6 7 8 9'), (36, 9))
        self.assertEqual(report.cpu_percent((100, 50), (200, 125)), 25)
        self.assertEqual(report.memory_info('MemTotal: 1024 kB')['MemTotal'], 1024**2)

    def test_package_parsing(self):
        text='Listing...\nlinux-image/stable 6.18 arm64 [upgradable from: 6.12]\n'
        self.assertEqual(report.packages_from_output(text), [('linux-image', '6.18')])

    def test_report_values(self):
        text=report.build_report(self.data())
        for expected in ['Brasília', 'CPU: 2.1%', 'Memória:', 'Swap:', '63.4 °C', '3.0 GiB', 'linux-image', '1 pacote', 'Índices atualizados']:
            self.assertIn(expected, text)

    def test_missing_temperature_and_stale_updates(self):
        data=self.data(); data.update(temperature=None, packages=None, fresh=False)
        text=report.build_report(data)
        self.assertIn('leitura indisponível', text)
        self.assertIn('Consulta indisponível', text)
        self.assertIn('desatualizado', text)
        self.assertNotIn('Nenhuma atualização', text)

    def test_apt_refresh_failure_still_lists_cached_packages(self):
        with patch.object(report.subprocess, 'run') as run:
            run.side_effect=[SimpleNamespace(returncode=100), SimpleNamespace(returncode=0, stdout='Listing...\n')]
            self.assertEqual(report.updates(), ([], False))
            self.assertIn('update', run.call_args_list[0].args[0])

    def test_once_per_day_and_next_day(self):
        with tempfile.TemporaryDirectory() as directory:
            sent=[]
            sender=lambda text: sent.append(text) or True
            for day in [27, 27, 28]:
                self.assertTrue(report.run_once(directory, datetime(2026,10,day,tzinfo=report.ZONE), self.data, sender))
            self.assertEqual(len(sent), 2)

    def test_failed_send_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(report.run_once(directory, collector=self.data, sender=lambda _:False))
            self.assertFalse((Path(directory)/'daily-report-date').exists())
            self.assertTrue(report.run_once(directory, collector=self.data, sender=lambda _:True))

    def test_long_update_list_limited(self):
        data=self.data(); data['packages']=[('p'+str(i),'1') for i in range(100)]
        text=report.build_report(data)
        self.assertIn('mais 88', text)
        self.assertLess(len(text),4096)


if __name__ == '__main__':
    unittest.main(verbosity=2)
