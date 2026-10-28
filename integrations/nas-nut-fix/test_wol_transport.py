import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import wol_transport as wol
import nas_recovery as recovery
from patch_wol import patched


class TransportTests(unittest.TestCase):
    def setup_transport(self, carrier='1'):
        return patch.object(wol.Path,'read_text',return_value=carrier)

    def test_ethernet_source_broadcast_and_exact_magic_packet(self):
        sock=MagicMock();sock.sendto.return_value=102
        factory=MagicMock();factory.return_value.__enter__.return_value=sock
        addr=json.dumps([{'addr_info':[{'family':'inet','scope':'global','local':'192.168.50.143','prefixlen':24}]}])
        with self.setup_transport(), patch.object(wol.subprocess,'run',return_value=MagicMock(stdout=addr)), patch.object(wol.socket,'socket',factory), patch.object(wol.time,'sleep'):
            result=wol.send_magic('6c:1f:f7:a8:b1:0d')
        sock.setsockopt.assert_any_call(wol.socket.SOL_SOCKET,wol.socket.SO_BINDTODEVICE,b'eth0\0')
        sock.bind.assert_called_once_with(('192.168.50.143',0))
        self.assertEqual(sock.sendto.call_count,3)
        packet,target=sock.sendto.call_args.args
        self.assertEqual(packet,b'\xff'*6+bytes.fromhex('6c1ff7a8b10d')*16)
        self.assertEqual(target,('192.168.50.255',9))
        self.assertEqual(result['interface'],'eth0')

    def test_disconnected_cable_never_opens_socket(self):
        with self.setup_transport('0'),patch.object(wol.socket,'socket') as sock:
            with self.assertRaises(RuntimeError):wol.send_magic('6c:1f:f7:a8:b1:0d')
            sock.assert_not_called()

    def test_invalid_mac_rejected_before_network_access(self):
        with patch.object(wol.socket,'socket') as sock:
            with self.assertRaises(ValueError):wol.send_magic('invalid')
            sock.assert_not_called()

    def test_patch_is_idempotent(self):
        source='def send_wol():\n    pass\n\ndef untouched():\n    return 42\n'
        self.assertEqual(patched(patched(source)),patched(source))
        self.assertIn('def untouched():\n    return 42',patched(source))

    def test_transport_failure_is_persisted_without_success_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state';recovery.mark_pending('test',path)
            clock=[0];messages=[];calls=[]
            boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            def sample():return dict(at=clock[0],boot_id=boot,status='OL',battery=95)
            def sleep(seconds):clock[0]+=seconds
            def fail():
                calls.append(clock[0]);raise OSError('send failed')
            result=recovery.recover(sample,lambda:False,lambda:True,lambda:True,fail,messages.append,
                                    lambda:False,path=path,clock=lambda:clock[0],sleep=sleep,
                                    stable_seconds=10,timeout=300)
            self.assertFalse(result)
            self.assertEqual(len(calls),3)
            self.assertTrue(all(b-a>=60 for a,b in zip(calls,calls[1:])))
            state=recovery.read_state(path)
            self.assertEqual(state['wake_attempts'],3)
            self.assertEqual(state['last_transport_error'],'OSError')
            self.assertTrue(state['pending'])
            self.assertFalse(any('WOL enviado' in message for message in messages))

if __name__=='__main__':unittest.main()
