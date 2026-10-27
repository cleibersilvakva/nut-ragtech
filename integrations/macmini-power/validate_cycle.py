#!/usr/bin/env python3
"""Authorized real suspend/resume validation; execute on Raspberry only."""
import json
from pathlib import Path
import subprocess
import sys
import time
from daemon import Actions

ROOT=Path(__file__).resolve().parent
CONFIG=dict(host='cleiber@192.168.50.9',key='/home/cleibersilva/.ssh/id_ed25519_macmini_power',
            known_hosts=str(ROOT/'known_hosts'),mac='ac:87:a3:36:59:ec',broadcast='192.168.50.255')
actions=Actions(CONFIG)

if __name__=='__main__':
    if '--rescue-wol' in sys.argv:
        time.sleep(45)
        for _ in range(3):
            actions.wake();time.sleep(30)
        raise SystemExit(0)
    before=actions.status()
    if not before:raise SystemExit('SSH restrito não funciona; nenhum teste de suspensão iniciado')
    if not Path('/usr/bin/ssh').exists():raise SystemExit('SSH ausente')
    rescue_log=(ROOT/'rescue-wol.log').open('a')
    child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--rescue-wol'],stdin=subprocess.DEVNULL,
                           stdout=rescue_log,stderr=rescue_log,start_new_session=True)
    print('Resgate WOL agendado no Raspberry; PID',child.pid,flush=True)
    if not actions.suspend():raise SystemExit('Solicitação de suspensão rejeitada; resgate WOL permanece agendado')
    print('Suspensão aceita; verificando indisponibilidade e retorno.',flush=True)
    offline=False;started=time.time();after=None
    while time.time()-started<150:
        time.sleep(5)
        status=actions.status()
        if not status:offline=True
        elif offline:
            after=status;break
    result=dict(offline_observed=offline,returned=bool(after),same_boot=bool(after and after['boot_id']==before['boot_id']),
                elapsed_seconds=round(time.time()-started),checked_at=time.time())
    (ROOT/'validation-result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2),flush=True)
    raise SystemExit(0 if result['offline_observed'] and result['returned'] and result['same_boot'] else 1)
