#!/bin/sh
# Run as the internet-monitor service user on Raspberry Pi (without sudo).
set -eu
cd "$(dirname "$0")"
python3 -B -m unittest test_hourly_report
install -m 644 hourly_report.py /opt/internet-monitor/hourly_report.py
python3 -B - <<'PY'
from datetime import datetime
from pathlib import Path
import subprocess
old=subprocess.check_output(['crontab','-l'],text=True)
data=Path('/opt/internet-monitor/data')
(data/('crontab-before-hourly-'+datetime.now().strftime('%Y%m%d%H%M%S')+'.txt')).write_text(old)
lines=[line for line in old.splitlines() if '# internet-hourly-telegram' not in line]
lines.append('*/5 * * * * /usr/bin/python3 -B /opt/internet-monitor/hourly_report.py >> /opt/internet-monitor/data/hourly-report.log 2>&1 # internet-hourly-telegram')
subprocess.run(['crontab','-'],input='\n'.join(lines)+'\n',text=True,check=True)
PY
cd /opt/internet-monitor
python3 -B hourly_report.py
