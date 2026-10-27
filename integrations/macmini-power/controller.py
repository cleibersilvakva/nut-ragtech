"""Persistent Mac mini power policy driven by fresh Raspberry UPS samples."""
import json
import time
from pathlib import Path


def write_json(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data));temp.replace(path)


class Controller:
    def __init__(self, state, actions, config):
        self.path=Path(state);self.actions=actions;self.config=config
        try:
            self.state=json.loads(self.path.read_text())
            if not isinstance(self.state,dict):raise ValueError()
        except FileNotFoundError:
            self.state={'phase':'idle','owned':False}
        except (OSError,ValueError):
            # Corrupt state must not permit unsolicited WOL.
            self.state={'phase':'disabled','owned':False}
        self.low_count=0;self.stable_since=None;self.last_sample=None

    def save(self):write_json(self.path,self.state)

    def step(self,sample,now):
        if not self.config.get('enabled') or self.state['phase']=='disabled':return
        valid=(isinstance(sample,dict) and sample.get('boot_id')==self.config['pi_boot_id']
               and 0<=now-sample.get('at',-1e9)<=20)
        try:
            battery=float(sample['battery']) if valid else -1
            valid=valid and 0<=battery<=100 and sample['status'] in ('OL','OB','OB LB')
        except (TypeError,KeyError,ValueError):valid=False
        if not valid:
            self.low_count=0;self.stable_since=None;return
        # Re-reading the same sample cannot establish consecutive observations.
        if sample['at']==self.last_sample:return
        if self.last_sample is not None and sample['at']-self.last_sample>20:
            self.low_count=0;self.stable_since=None
        self.last_sample=sample['at']
        on_battery='OB' in sample['status']
        if on_battery or battery<self.config['wake_battery']:
            self.stable_since=None
        elif self.stable_since is None:self.stable_since=now
        ready=(self.stable_since is not None and now-self.stable_since>=self.config['stable_seconds'])
        phase=self.state['phase']
        if phase=='pending':
            if now-self.state['requested_at']<15:return
            if not self.actions.status():
                self.state['phase']='sleeping';self.save()
                self.actions.notify('💤 Suspensão solicitada ao Mac mini; ele ficou inacessível na rede. Aguardando recuperação segura da energia.')
            elif now-self.state['requested_at']>=90:
                self.state['phase']='sleeping';self.save()
                self.actions.notify('⚠️ Mac mini ainda responde após a solicitação de suspensão. A suspensão não foi confirmada.')
            return
        if self.state.get('owned') and phase in ('sleeping','waking'):
            if not ready:return
            if phase=='waking' and now-self.state['last_wake']<30:return
            status=self.actions.status()
            if status:
                same=status.get('boot_id')==self.state.get('mac_boot_id')
                self.state={'phase':'idle','owned':False};self.save()
                self.actions.notify('✅ Mac mini voltou a responder. '+('Mesmo boot: retomada sem reinicialização.' if same else 'Foi identificado um novo boot.'))
                return
            attempts=self.state.get('wake_attempts',0)
            if attempts>=3:
                if not self.state.get('wake_failed'):
                    self.state['wake_failed']=True;self.save()
                    self.actions.notify('⚠️ Mac mini não respondeu após três tentativas de WOL; verificação manual necessária.')
                return
            if now-self.state.get('last_wake',-1e9)<60:return
            self.actions.wake()
            self.state.update(phase='waking',last_wake=now,wake_attempts=attempts+1)
            self.save();self.actions.notify('🔌 Energia estável e bateria suficiente. Wake-on-LAN enviado ao Mac mini; aguardando resposta.')
            return
        if not on_battery:
            self.low_count=0
            if phase=='idle' and self.state.get('suspend_attempts'):
                self.state={'phase':'idle','owned':False};self.save()
            return
        if battery>self.config['suspend_battery']:
            self.low_count=0;return
        self.low_count+=1
        if self.low_count<3 or now-self.state.get('last_suspend',-1e9)<60:return
        attempts=self.state.get('suspend_attempts',0)
        if attempts>=3:return
        status=self.actions.status()
        self.state.update(last_suspend=now,suspend_attempts=attempts+1)
        if not status:
            self.save()
            if attempts==0:self.actions.notify('⚠️ Mac mini não está acessível; nenhuma suspensão solicitada e nenhum WOL automático será assumido.')
            return
        # Persist intent before external action. A failed command never grants WOL ownership.
        self.save()
        if self.actions.suspend():
            self.state.update(phase='pending',owned=True,requested_at=now,mac_boot_id=status['boot_id'])
            self.save();self.actions.notify(f'🔋 Nobreak na bateria ({battery:.0f}%). Suspensão do Mac mini solicitada.')
        else:
            self.actions.notify('⚠️ Falha ao solicitar suspensão do Mac mini. Nova tentativa será limitada.')
