#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ "$(id -u)" = 0 ] || { echo 'Execute com sudo.'; exit 1; }
python3 -B -m unittest discover -s tests -v
systemd-analyze verify macmini-ups-power.service
install -d -m 755 /opt/macmini-ups-power
install -d -m 700 /etc/macmini-ups-power /var/lib/macmini-ups-power
install -m 644 controller.py daemon.py /opt/macmini-ups-power/
install -m 600 /home/cleibersilva/.ssh/id_ed25519_macmini_power /etc/macmini-ups-power/id_ed25519
install -m 600 known_hosts /etc/macmini-ups-power/known_hosts
python3 -B - <<'PYINSTALL'
from pathlib import Path
import ast,shutil,time,json,sys
sys.path.insert(0,'/opt/macmini-ups-power')
from daemon import Actions
config=dict(enabled=True,host='cleiber@192.168.50.9',key='/etc/macmini-ups-power/id_ed25519',
            known_hosts='/etc/macmini-ups-power/known_hosts',mac='ac:87:a3:36:59:ec',broadcast='192.168.50.255',
            suspend_battery=85,wake_battery=80,stable_seconds=180)
if not Actions(config).status():
    raise SystemExit('SSH restrito não validado. Instale primeiro no Mac mini; serviço não foi ativado.')
path=Path('/etc/macmini-ups-power.json')
path.write_text(json.dumps(config,indent=2));path.chmod(0o600)
monitor=Path('/opt/ragtech-monitor/ragtech_nut.py');source=monitor.read_text()
backup=monitor.with_name('ragtech_nut.py.before-macmini-power-'+str(int(time.time())))
if 'from daemon import publish_sample' not in source:
    shutil.copy2(monitor,backup)
    source=source.replace('import json\n', 'import json\nimport sys as _power_sys\n_power_sys.path.insert(0, "/opt/macmini-ups-power")\nfrom daemon import publish_sample\n',1)
    anchor='            set_cached_ups(data)'
    if source.count(anchor)!=1:raise SystemExit('Ponto de integração não encontrado; arquivo preservado')
    source=source.replace(anchor,anchor+'\n            publish_sample(data)',1)
    ast.parse(source)
    monitor.write_text(source)
print('SSH restrito validado; heartbeat integrado sem alterar funções UPS ou NAS.')
PYINSTALL
install -m 644 macmini-ups-power.service /etc/systemd/system/macmini-ups-power.service
systemctl daemon-reload
systemctl restart ragtech-monitor
sleep 8
python3 -B - <<'PYINSTALL'
import json,time
from pathlib import Path
s=json.loads(Path('/run/ragtech-power/sample.json').read_text())
assert 0<=time.time()-s['at']<20, 'Sem amostra recente; não ativar'
print('Amostra recente validada:',s['status'],s['battery'])
PYINSTALL
systemctl enable --now macmini-ups-power
systemctl is-active ragtech-monitor macmini-ups-power nut-server nut-monitor
printf '%s\n' 'Automação habilitada: suspender OB ≤85%; acordar OL ≥80% estável 180s.'
