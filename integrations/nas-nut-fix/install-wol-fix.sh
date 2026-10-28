#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ "$(id -u)" = 0 ] || { echo 'Execute com sudo.'; exit 1; }
python3 -B -m unittest -v test_recovery test_wol_transport
python3 -B - <<'PY'
from pathlib import Path
import ast, shutil, subprocess, time
from patch_wol import patched
status=subprocess.check_output(['upsc','ragtech@127.0.0.1','ups.status'],text=True).split()
if 'OL' not in status or any(x in status for x in ['OB','FSD','LB']):
    raise SystemExit('UPS precisa estar em energia normal, sem estado crítico.')
monitor=Path('/opt/ragtech-monitor/ragtech_nut.py')
updated=patched(monitor.read_text());ast.parse(updated)
before=ast.parse(monitor.read_text());after=ast.parse(updated)
for node in before.body:
    if isinstance(node,ast.FunctionDef) and node.name!='send_wol':
        other=next(n for n in after.body if isinstance(n,ast.FunctionDef) and n.name==node.name)
        assert ast.dump(node)==ast.dump(other),node.name
backup=Path('/var/backups')/('nas-wol-ethernet-'+str(int(time.time())))
backup.mkdir(mode=0o700)
for name in ['ragtech_nut.py','nas_recovery.py','wol_transport.py']:
    path=monitor.parent/name
    if path.exists():shutil.copy2(path,backup/name)
for name in ['wol_transport.py','nas_recovery.py']:
    shutil.copy2(name,monitor.parent/name);(monitor.parent/name).chmod(0o644)
monitor.write_text(updated)
print('Backup:',backup)
PY
systemctl restart ragtech-monitor
systemctl is-active ragtech-monitor nut-monitor macmini-ups-power
printf '%s\n' 'WOL Ethernet instalado. Cota persistente preservada; nenhum desligamento executado.'
