from pathlib import Path
import json,os,subprocess,sys,unittest
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from daemon import Actions
ROOT=Path(__file__).resolve().parents[1]
class TransportTests(unittest.TestCase):
    def test_forced_wrapper_rejects_shell_and_other_commands(self):
        for command in ['reboot','shutdown','bash','status; reboot','suspend now','']:
            result=subprocess.run(['sh',str(ROOT/'macmini-power-ssh')],env={**os.environ,'SSH_ORIGINAL_COMMAND':command},capture_output=True)
            self.assertEqual(result.returncode,126)
    def test_helper_status_and_invalid_args_never_suspend(self):
        result=subprocess.run([sys.executable,str(ROOT/'macmini-power-control'),'status'],capture_output=True,text=True,check=True)
        self.assertTrue(json.loads(result.stdout)['boot_id'])
        for command in ['shutdown','reboot','suspend; reboot']:
            result=subprocess.run([sys.executable,str(ROOT/'macmini-power-control'),command],capture_output=True)
            self.assertNotEqual(result.returncode,0)
    def test_wol_packet_target_mac_and_count(self):
        config=dict(mac='ac:87:a3:36:59:ec',broadcast='192.168.50.255')
        with patch('daemon.socket.socket') as factory:
            sock=factory.return_value.__enter__.return_value
            Actions(config).wake()
            self.assertEqual(sock.sendto.call_count,3)
            payload,target=sock.sendto.call_args.args
            self.assertEqual(target,('192.168.50.255',9))
            self.assertEqual(payload,b'\xff'*6+bytes.fromhex('ac87a33659ec')*16)
