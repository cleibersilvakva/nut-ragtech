#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ "$(id -u)" = 0 ] || { echo 'Execute com sudo.'; exit 1; }
python3 -B -m unittest -v test_raspberry_integration
python3 -B - <<'PYINSTALL'
from pathlib import Path
import ast,shutil,sqlite3,time,os,pwd
import patch_raspberry
backup=Path('/opt/ragtech-monitor')/('backup-macmini-api-'+time.strftime('%Y%m%d-%H%M%S'))
backup.mkdir(mode=0o700)
items=patch_raspberry.patches()
for path,transform in items:
    source=path.read_text()
    ast.parse(transform(source))
    shutil.copy2(path,backup/(path.parent.name+'-'+path.name))
for path in [Path('/etc/macmini-speedtest.json'),Path('/opt/ragtech-monitor/macmini_speedtest_client.py'),Path('/opt/internet-monitor/macmini_speedtest_client.py')]:
    if path.exists():shutil.copy2(path,backup/(path.parent.name+'-'+path.name))
db=Path('/opt/internet-monitor/data/events.db')
if db.exists():
    with sqlite3.connect(db) as original,sqlite3.connect(backup/'events.db') as copy:original.backup(copy)
for directory in ['/opt/ragtech-monitor','/opt/internet-monitor']:
    dest=Path(directory)/'macmini_speedtest_client.py'
    shutil.copyfile('macmini_speedtest_client.py',dest)
    dest.chmod(0o644)
shutil.copyfile('config.json','/etc/macmini-speedtest.json')
os.chown('/etc/macmini-speedtest.json',0,pwd.getpwnam('cleibersilva').pw_gid)
Path('/etc/macmini-speedtest.json').chmod(0o640)
for path,transform in items:
    temp=path.with_suffix('.macmini-new')
    temp.write_text(transform(path.read_text()))
    stat=path.stat();os.chown(temp,stat.st_uid,stat.st_gid);temp.chmod(stat.st_mode&0o777)
    temp.replace(path)
print('Backup:',backup)
PYINSTALL
systemctl restart ragtech-monitor internet-monitor
sleep 5
systemctl is-active ragtech-monitor internet-monitor nut-server nut-monitor
# This reuses the API's recent measurement and sends the first real integration report.
python3 -B - <<'PYCHECK'
import sys
sys.path.insert(0,'/opt/ragtech-monitor')
import ragtech_nut
ragtech_nut._net_worker()
PYCHECK
