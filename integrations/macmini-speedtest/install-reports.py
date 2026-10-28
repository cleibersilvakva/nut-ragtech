"""Run as the existing internet-monitor service user on Raspberry Pi."""
import ast
from datetime import datetime
import os
from pathlib import Path
import shutil
import signal
import subprocess

root=Path('/opt/internet-monitor')
subprocess.run(['python3','-B','-m','unittest','test_hourly_report','test_daily_summary'],check=True)
config=root/'config.py';source=config.read_text();tree=ast.parse(source)
node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SPEEDTEST_INTERVAL_S' for t in n.targets))
lines=source.splitlines(keepends=True);lines[node.lineno-1:node.end_lineno]=['SPEEDTEST_INTERVAL_S = 3600\n'];updated=''.join(lines);ast.parse(updated)
old=subprocess.check_output(['crontab','-l'],text=True)
backup=root/'data'/('backup-reports-'+datetime.now().strftime('%Y%m%d%H%M%S'));backup.mkdir(mode=0o700)
shutil.copy2(config,backup/'config.py');(backup/'config.py').chmod(0o600)
(backup/'crontab.txt').write_text(old)
for name in ['hourly_report.py','daily_summary.py']:
    dest=root/name
    if dest.exists():shutil.copy2(dest,backup/name)
    if Path(name).resolve()!=dest.resolve():shutil.copy2(name,dest)
lines=[line for line in old.splitlines() if '/opt/internet-monitor/report.py' not in line and '# internet-hourly-telegram' not in line and '# internet-daily-telegram' not in line]
lines.extend([
'*/5 * * * * /usr/bin/python3 -B /opt/internet-monitor/hourly_report.py >> /opt/internet-monitor/data/hourly-report.log 2>&1 # internet-hourly-telegram',
'*/5 * * * * /usr/bin/python3 -B /opt/internet-monitor/daily_summary.py >> /opt/internet-monitor/data/daily-summary.log 2>&1 # internet-daily-telegram'])
config.write_text(updated)
subprocess.run(['crontab','-'],input='\n'.join(lines)+'\n',text=True,check=True)
# The running process cached config.py; restart only this user's exact monitor.
if source!=updated:
    pid=int(subprocess.check_output(['systemctl','show','internet-monitor.service','-p','MainPID','--value'],text=True))
    proc=Path('/proc')/str(pid)
    if pid<=1 or proc.stat().st_uid!=os.getuid() or (proc/'cmdline').read_bytes().split(b'\0')[:2]!=[b'/usr/bin/python3',b'/opt/internet-monitor/monitor.py']:
        raise SystemExit('Configuração salva, mas reinício manual do internet-monitor necessário: processo inesperado.')
    # Restart=on-failure restarts after SIGKILL; no root access needed for own process.
    os.kill(pid,signal.SIGKILL)
print('Backup privado:',backup)
print('Coleta 3600s; Telegram horário; consolidado diário após 07:00 America/Sao_Paulo.')
