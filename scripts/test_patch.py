import os, json, tempfile
import ast
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch
from patch_monitor import patched


class PatchTests(unittest.TestCase):
    def test_actual_production_patch(self):
        path = Path(__file__).with_name('ragtech_nut.py')
        if not path.exists():
            self.skipTest('Production path only available on Raspberry')
        source = path.read_text()
        updated = patched(source)
        ast.parse(updated)
        self.assertEqual(patched(updated), updated)
        # Credentials and UPS/recovery functions remain byte-for-byte intact.
        old_tree, new_tree = ast.parse(source), ast.parse(updated)
        names = ['read_ups', 'push_to_nut', 'power_restored_sequence', 'clear_fsd', 'send_wol']
        for name in names:
            old = next(n for n in old_tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            new = next(n for n in new_tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            self.assertEqual(ast.dump(old), ast.dump(new))
        namespace = {'__name__': 'monitor_test'}
        with tempfile.TemporaryDirectory() as d:
            credentials = Path(d) / 'credentials.json'
            credentials.write_text(json.dumps({'nut_pass':'test','bot_token':'test','chat_id':'test'}))
            with patch.dict(os.environ, {'RAGTECH_CREDENTIALS_FILE':str(credentials)}), patch.dict(sys.modules, {'serial': types.ModuleType('serial')}), patch.dict(sys.modules, {'daemon':types.SimpleNamespace(publish_sample=lambda data:None)}):
                exec(compile(updated, '<patched-monitor>', 'exec'), namespace)
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok":true}'
        with patch.object(namespace['urllib'].request, 'urlopen', return_value=response) as request:
            self.assertTrue(namespace['send_telegram']('boot', parse_mode=None))
            self.assertNotIn(b'parse_mode', request.call_args.args[0].data)
        with patch.object(namespace['urllib'].request, 'urlopen', side_effect=OSError):
            self.assertFalse(namespace['send_telegram']('test'))
        with patch.object(namespace['urllib'].request, 'urlopen', return_value=response):
            response.__enter__.return_value.read.return_value = b'{"ok":false}'
            self.assertFalse(namespace['send_telegram']('test'))
        # One main-loop iteration: no network, threads, UPS writes, WOL or Telegram.
        namespace.update(read_ups=lambda: None, load_last_status=lambda: None)
        with patch.object(namespace['threading'], 'Thread') as thread, patch.object(namespace['time'], 'sleep', side_effect=InterruptedError):
            with self.assertRaises(InterruptedError):
                namespace['main']()
            self.assertEqual(thread.call_count, 3)
