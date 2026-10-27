#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ "$(id -u)" = 0 ] || { echo 'Execute com sudo.'; exit 1; }
python3 -B -m unittest -v test_recovery test_patch_pi
python3 -B - <<'PYINSTALL'
from pathlib import Path
import subprocess,time,shutil,ast
from patch_pi import patched
state=subprocess.check_output(['upsc','ragtech@127.0.0.1','ups.status'],text=True).split()
if 'OL' not in state or 'FSD' in state:raise SystemExit('UPS não está normal; instalação cancelada')
backup=Path('/var/backups')/('nut-safe-recovery-'+str(int(time.time())))
backup.mkdir(mode=0o700)
monitor=Path('/opt/ragtech-monitor/ragtech_nut.py')
source=patched(monitor.read_text());ast.parse(source)
for path in [monitor,Path('/etc/nut/upsmon.conf'),Path('/etc/systemd/system/nut-monitor.service.d/restart.conf')]:
    if path.exists():shutil.copy2(path,backup/path.name)
shutil.copy2('nas_recovery.py','/opt/ragtech-monitor/nas_recovery.py')
Path('/opt/ragtech-monitor/nas_recovery.py').chmod(0o644)
monitor.write_text(source)
conf=Path('/etc/nut/upsmon.conf');lines=conf.read_text().splitlines()
lines=[line for line in lines if not line.strip().startswith('SHUTDOWNEXIT ')]
conf.write_text('\n'.join(lines)+'\nSHUTDOWNEXIT no\n')
p=Path('/etc/systemd/system/nut-monitor.service.d/restart.conf');p.parent.mkdir(parents=True,exist_ok=True)
p.write_text('[Service]\nRestart=on-failure\nRestartSec=30\n')
print('Backup:',backup)
PYINSTALL
systemctl daemon-reload
systemctl restart nut-monitor ragtech-monitor
sleep 6
systemctl is-active nut-monitor ragtech-monitor macmini-ups-power
upsc ragtech@127.0.0.1 ups.status
printf '%s\n' 'Recuperação segura implantada. Nenhum shutdown ou WOL executado pelo instalador.'
