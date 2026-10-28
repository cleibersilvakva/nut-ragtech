"""Explicit real WOL test: user powers NAS off; Pi observes and wakes it."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
sys.path.insert(0, '/opt/ragtech-monitor')
from wol_transport import send_magic
BASE=Path(__file__).resolve().parent
RESULT=BASE/'manual-wol-result.json'

def report(stage, **extra):
    data=dict(stage=stage,at=time.time(),**extra)
    RESULT.write_text(json.dumps(data))
    print(json.dumps(data),flush=True)

def online():
    for port in (445,9443):
        try:
            with socket.create_connection(('192.168.50.110',port),timeout=2):return True
        except OSError:pass
    return False

def normal():
    try:
        result=subprocess.run(['upsc','ragtech@127.0.0.1'],capture_output=True,text=True,timeout=5,check=True)
        data=dict(line.split(': ',1) for line in result.stdout.splitlines() if ': ' in line)
        return data.get('ups.status')=='OL' and float(data.get('battery.charge','0'))>=80
    except (OSError,ValueError,subprocess.SubprocessError):return False

report('armed',message='Waiting up to 15 minutes for manual normal poweroff')
end=time.monotonic()+900
absent=0
while time.monotonic()<end:
    if not normal():report('aborted',reason='UPS not normal');sys.exit(1)
    absent=0 if online() else absent+1
    if absent>=3:break
    time.sleep(5)
else:report('expired',reason='No shutdown observed');sys.exit(1)
report('offline_observed')
# Leave shutdown time to complete; require stable mains throughout.
for _ in range(36):
    if not normal():report('aborted',reason='UPS not normal');sys.exit(1)
    if online():report('returned_before_wol');sys.exit(0)
    time.sleep(5)
for attempt in range(1,4):
    if not normal():report('aborted',reason='UPS not normal');sys.exit(1)
    if online():report('returned',attempts=attempt-1);sys.exit(0)
    receipt=send_magic('6c:1f:f7:a8:b1:0d')
    report('wol_sent',attempt=attempt,receipt=receipt)
    good=0
    for _ in range(36):
        if not normal():report('aborted',reason='UPS not normal');sys.exit(1)
        good=good+1 if online() else 0
        if good>=3:report('returned',attempts=attempt);sys.exit(0)
        time.sleep(5)
report('failed',reason='No return after three WOL attempts')
