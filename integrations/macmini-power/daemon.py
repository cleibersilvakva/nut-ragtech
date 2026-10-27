#!/usr/bin/env python3
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from controller import Controller,write_json

CONFIG=Path('/etc/macmini-ups-power.json')
SAMPLE=Path('/run/ragtech-power/sample.json')


def publish_sample(data):
    try:
        write_json(SAMPLE,dict(at=time.time(),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                               battery=float(data['battery.charge']),status=data['ups.status']))
    except Exception:
        logging.warning('Não foi possível atualizar a amostra para controle do Mac mini')


class Actions:
    def __init__(self,config):self.config=config
    def ssh(self,command):
        return subprocess.run(['ssh','-i',self.config['key'],'-o','BatchMode=yes','-o','IdentitiesOnly=yes',
            '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+self.config['known_hosts'],
            '-o','ConnectTimeout=5',self.config['host'],command],capture_output=True,text=True,timeout=10)
    def status(self):
        try:
            result=self.ssh('status')
            data=json.loads(result.stdout) if result.returncode==0 else None
            return data if isinstance(data,dict) and data.get('boot_id') else None
        except Exception:return None
    def suspend(self):
        try:
            result=self.ssh('suspend')
            return result.returncode==0 and result.stdout.strip()=='accepted'
        except Exception:return False
    def wake(self):
        mac=bytes.fromhex(self.config['mac'].replace(':',''))
        packet=b'\xff'*6+mac*16
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1)
            for _ in range(3):sock.sendto(packet,(self.config['broadcast'],9))
    def notify(self,text):
        sys.path.insert(0,'/opt/ragtech-monitor')
        from ragtech_nut import send_telegram
        send_telegram(text,parse_mode=None)


if __name__=='__main__':
    logging.basicConfig(level=logging.INFO)
    config=json.loads(CONFIG.read_text())
    config['pi_boot_id']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    controller=Controller('/var/lib/macmini-ups-power/state.json',Actions(config),config)
    while True:
        try:
            try:sample=json.loads(SAMPLE.read_text())
            except (OSError,ValueError):sample=None
            controller.step(sample,time.time())
        except Exception:logging.exception('Falha no controle de energia do Mac mini; tentando novamente')
        time.sleep(5)
