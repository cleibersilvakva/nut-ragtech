"""NAS recovery only after fresh stable mains, adequate battery and observed shutdown."""
import json
from pathlib import Path
import threading
import time
LOCK=threading.Lock()
STATE=Path('/var/lib/ragtech-monitor/nas-recovery.json')


def read_state(path=STATE):
    try:
        state=json.loads(Path(path).read_text())
        return state if isinstance(state,dict) else {'disabled':True}
    except FileNotFoundError:return {'pending':False}
    except (OSError,ValueError):return {'disabled':True}


def save_state(state,path=STATE):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(state));temp.replace(path)


def mark_pending(reason,path=STATE):
    with LOCK:
        state=read_state(path)
        if not state.get('pending') and not state.get('disabled'):
            save_state({'pending':True,'reason':reason,'at':time.time(),'wake_attempts':0},path)


def record_critical(data):
    status=data.get('ups.status','').split()
    if 'OB' in status and 'LB' in status:mark_pending('OB LB observed')


class Policy:
    def __init__(self,now,boot_id,stable_seconds=180,timeout=7200,attempts=0):
        self.started=now;self.boot_id=boot_id;self.stable_seconds=stable_seconds;self.timeout=timeout
        self.stable_since=None;self.last_sample=None;self.offline_count=0
        self.cleared=False;self.wake_attempts=attempts;self.last_wake=-1e12;self.online_count=0
    def step(self,sample,online,gateway,now):
        if now-self.started>=self.timeout:return 'timeout'
        try:
            valid=(sample['boot_id']==self.boot_id and 0<=now-sample['at']<=20 and 0<=float(sample['battery'])<=100)
        except (KeyError,TypeError,ValueError):valid=False
        if not valid or not gateway:
            self.stable_since=None;self.offline_count=0;return 'wait'
        stamp=sample['at']
        if self.last_sample is not None and stamp-self.last_sample>20:
            self.stable_since=None;self.offline_count=0
        distinct=stamp!=self.last_sample
        self.last_sample=stamp
        if sample['status']!='OL' or float(sample['battery'])<80:
            self.stable_since=None
            if sample['status']!='OL':self.cleared=False
            return 'wait'
        if self.stable_since is None:self.stable_since=now
        if distinct:
            self.offline_count=0 if online else self.offline_count+1
            self.online_count=self.online_count+1 if online else 0
        stable=now-self.stable_since>=self.stable_seconds
        if not stable:return 'wait'
        if self.wake_attempts and online and self.online_count>=3:return 'complete'
        if self.cleared and online and self.online_count>=3:return 'complete'
        if self.offline_count<3:return 'wait'
        if not self.cleared:return 'clear'
        if self.wake_attempts>=3:return 'failed' if now-self.last_wake>=120 else 'wait'
        if now-self.last_wake<60:return 'wait'
        return 'wake'


def recover(read_sample,is_online,gateway_ok,clear_fsd,send_wol,notify,has_fsd,
            path=STATE,clock=time.time,sleep=time.sleep,stable_seconds=180,timeout=7200):
    state=read_state(path)
    if state.get('disabled'):
        notify('⚠️ Recuperação NAS desabilitada: estado persistente inválido. Verificação manual necessária.');return False
    if not state.get('pending') and has_fsd():
        mark_pending('Existing FSD observed',path);state=read_state(path)
    if not state.get('pending'):return True
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    policy=Policy(clock(),boot,stable_seconds,timeout,state.get('wake_attempts',0))
    notify('🔌 Recuperação NAS pendente. Aguardando NAS inacessível, energia estável por 3 min e bateria ≥80%.')
    while True:
        sample=read_sample();online=is_online();gateway=gateway_ok()
        action=policy.step(sample,online,gateway,clock())
        if action in ('timeout','failed'):
            notify('⚠️ Recuperação NAS não concluída. Limite de espera/tentativas atingido; nenhum WOL adicional será enviado.');return False
        if action=='complete':
            with LOCK:save_state({'pending':False,'completed_at':clock()},path)
            notify('✅ NAS voltou a responder na rede após a recuperação.');return True
        if action=='clear':
            # Only reached after observed absence and stable power. Never clear FSD while waiting for NAS shutdown.
            if clear_fsd():policy.cleared=True
            else:
                notify('⚠️ Não foi possível limpar FSD; recuperação NAS interrompida sem WOL.');return False
        elif action=='wake':
            # Recheck the latest sample/route immediately before the external action.
            check=policy.step(read_sample(),is_online(),gateway_ok(),clock())
            if check=='wake':
                with LOCK:
                    state=read_state(path);state['wake_attempts']=policy.wake_attempts+1;save_state(state,path)
                send_wol();policy.wake_attempts+=1;policy.last_wake=clock()
                notify('🔌 Condições seguras confirmadas; WOL enviado ao NAS. Aguardando resposta.')
        sleep(5)
