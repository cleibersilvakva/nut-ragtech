#!/usr/bin/env python3
"""Run on Raspberry before starting NAS validation. Does not change production UPS state."""
from pathlib import Path
import json,socket,subprocess,sys,time
sys.path.insert(0,'/opt/ragtech-monitor')
from nas_recovery import recover,save_state
ROOT=Path(__file__).resolve().parent


def online():
    return subprocess.run(['ping','-c','1','-W','1','192.168.50.110'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0


def sample():
    try:return json.loads(Path('/run/ragtech-power/sample.json').read_text())
    except (OSError,ValueError):return None


def gateway():
    return subprocess.run(['ping','-c','1','-W','1','192.168.50.1'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0


def wake():
    packet=b'\xff'*6+bytes.fromhex('6c1ff7a8b10d')*16
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1)
        for _ in range(3):sock.sendto(packet,('192.168.50.255',9))


if __name__=='__main__':
    if not online():raise SystemExit('NAS precisa estar online antes de iniciar a validação')
    print('Supervisor pronto. Aguardando queda de resposta do NAS após teste autorizado.',flush=True)
    end=time.monotonic()+600;misses=0
    while time.monotonic()<end:
        misses=0 if online() else misses+1
        if misses>=3:break
        time.sleep(5)
    if misses<3:raise SystemExit('NAS não ficou inacessível; não enviar WOL')
    print('NAS inacessível em três consultas; iniciando recuperação segura de validação.',flush=True)
    path=ROOT/'validation-recovery-state.json'
    save_state({'pending':True,'reason':'isolated real validation','wake_attempts':0},path)
    ok=recover(sample,online,gateway,lambda:True,wake,lambda text:print(text,flush=True),lambda:False,
               path=path,timeout=900)
    (ROOT/'validation-result.json').write_text(json.dumps({'returned':ok,'at':time.time()},indent=2))
    raise SystemExit(0 if ok else 1)
