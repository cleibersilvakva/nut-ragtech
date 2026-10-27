#!/usr/bin/env python3
"""Temporarily stop production upsmon; restore it on failed/completed dry tests."""
import argparse
import subprocess
from isolated_nut_test import run_test


def safe_state(run=subprocess.run):
    result=run(['/usr/bin/upsc','ragtech@192.168.50.143','ups.status'],capture_output=True,text=True,timeout=10)
    tokens=result.stdout.split()
    if result.returncode or 'OL' not in tokens or 'FSD' in tokens or 'OB' in tokens:
        raise RuntimeError('Production UPS is not normal; validation cancelled before stopping client')


def restore_client(run=subprocess.run):
    result=run(['/usr/bin/systemctl','is-system-running'],capture_output=True,text=True,timeout=10)
    if result.stdout.strip()=='stopping':return
    result=run(['/usr/bin/systemctl','start','nas-nut-client.service'],capture_output=True,text=True,timeout=30)
    if result.returncode:raise RuntimeError('Failed to restore NAS production client')


def validate(real=False,run=subprocess.run,test=run_test):
    safe_state(run)
    try:
        run(['/usr/bin/systemctl','stop','nas-nut-client.service'],check=True,capture_output=True,text=True,timeout=30)
        result=run(['/usr/bin/systemctl','is-active','nas-nut-client.service'],capture_output=True,text=True,timeout=10)
        if result.returncode==0:raise RuntimeError('Production client is still active; do not start another upsmon')
        return test(real=real,privsep=True)
    finally:
        restore_client(run)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real-poweroff',action='store_true')
    parser.add_argument('--restore-only',action='store_true')
    args=parser.parse_args()
    if args.restore_only:restore_client()
    else:validate(real=args.real_poweroff)
