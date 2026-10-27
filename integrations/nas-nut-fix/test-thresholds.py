#!/usr/bin/env python3
"""Apply or restore explicitly requested temporary test thresholds on Raspberry."""
import ast,json,shutil,subprocess,sys,time
from pathlib import Path
STATE=Path('/var/lib/ragtech-monitor/temporary-thresholds.json')
CONF=Path('/etc/macmini-ups-power.json')
MONITOR=Path('/opt/ragtech-monitor/ragtech_nut.py')
if len(sys.argv)!=2 or sys.argv[1] not in ('apply','restore'):raise SystemExit('Use apply or restore')
status=subprocess.check_output(['upsc','ragtech@127.0.0.1','ups.status'],text=True).split()
if 'OL' not in status or 'FSD' in status:raise SystemExit('UPS fora de OL normal: nenhuma alteração aplicada')
config=json.loads(CONF.read_text());source=MONITOR.read_text();tree=ast.parse(source)
function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='read_ups')
assignment=next(n for n in ast.walk(function) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='low_battery' for t in n.targets))
old=ast.get_source_segment(source,assignment)
if sys.argv[1]=='apply':
    if STATE.exists() and json.loads(STATE.read_text()).get('active'):raise SystemExit('Limiares temporários já ativos; não sobrescrever baseline')
    baseline={'active':True,'previous_mac':config['suspend_battery'],'previous_nas_assignment':old,'applied_at':time.time()}
    mac=86;new='low_battery = battery_pct <= 88'
else:
    baseline=json.loads(STATE.read_text())
    if not baseline.get('active'):raise SystemExit('Nenhum teste temporário ativo')
    mac=baseline['previous_mac'];new=baseline['previous_nas_assignment']
updated=source.replace(old,new,1);ast.parse(updated)
backup=Path('/var/backups')/('nut-test-thresholds-'+str(int(time.time())));backup.mkdir(mode=0o700)
shutil.copy2(CONF,backup/CONF.name);shutil.copy2(MONITOR,backup/MONITOR.name)
config['suspend_battery']=mac
if sys.argv[1]=='apply':STATE.write_text(json.dumps(baseline,indent=2));STATE.chmod(0o600)
CONF.write_text(json.dumps(config,indent=2));CONF.chmod(0o600);MONITOR.write_text(updated)
subprocess.run(['systemctl','restart','ragtech-monitor','macmini-ups-power'],check=True)
if sys.argv[1]=='restore':baseline['active']=False;baseline['restored_at']=time.time();STATE.write_text(json.dumps(baseline,indent=2))
print('Aplicado:',new,'; suspensão Mac:',mac,'%; backup:',backup)
print('Restauração: sudo python3 /home/cleibersilva/.local/share/nas-nut-fix/test-thresholds.py restore')
