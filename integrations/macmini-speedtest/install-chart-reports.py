"""Deploy daily chart as the internet-monitor owner, without root."""
from datetime import datetime
from pathlib import Path
import ast
import shutil
import subprocess
import sys

root=Path('/opt/internet-monitor')
python=Path.home()/'.local/share/internet-report-venv/bin/python'
if not python.exists():
    raise SystemExit('Crie o venv internet-report-venv e instale requirements-reports.txt primeiro.')
subprocess.run([str(python),'-B','-m','unittest','test_daily_chart'],check=True)
# Hourly collection is already configured; no monitor restart is required.
tree=ast.parse((root/'config.py').read_text())
interval=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='SPEEDTEST_INTERVAL_S' for target in node.targets))
if interval!=3600:raise SystemExit('Configure a coleta para3600s antes de instalar o gráfico.')
old=subprocess.check_output(['crontab','-l'],text=True)
backup=root/'data'/('backup-chart-'+datetime.now().strftime('%Y%m%d%H%M%S'));backup.mkdir(mode=0o700)
(backup/'crontab.txt').write_text(old)
dest=root/'daily_chart.py'
if dest.exists():shutil.copy2(dest,backup/dest.name)
if Path('daily_chart.py').resolve()!=dest.resolve():shutil.copy2('daily_chart.py',dest)
lines=[line for line in old.splitlines() if not any(value in line for value in ['# internet-hourly-telegram','# internet-daily-telegram','# internet-daily-chart','/opt/internet-monitor/report.py'])]
lines.append(f'*/5 * * * * {python} -B /opt/internet-monitor/daily_chart.py >> /opt/internet-monitor/data/daily-chart.log 2>&1 # internet-daily-chart')
subprocess.run(['crontab','-'],input='\n'.join(lines)+'\n',text=True,check=True)
print('Backup:',backup)
print('Avisos horários desativados; gráfico diário08hBrasília; coleta3600s preservada.')
