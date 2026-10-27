#!/usr/bin/env python3
"""Exercise installed upsmon against a loopback-only synthetic UPS.
Default action only creates a private marker. Real poweroff requires root and
an explicit --real-poweroff flag, used only by a dedicated validation service.
"""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import pwd
import grp
import shlex
import socketserver
import subprocess
import tempfile
import threading
import time


def run_test(real=False,privsep=False):
    privsep = privsep or real
    if privsep and os.geteuid()!=0:raise RuntimeError('Real validation requires root')
    if real:
        state=subprocess.check_output(['/usr/bin/upsc','ragtech@192.168.50.143','ups.status'],text=True,timeout=8).split()
        if 'OL' not in state or 'FSD' in state or 'OB' in state:raise RuntimeError('Production UPS is not safe for validation')
    state={'status':'OL','logins':0,'gets':0}
    class Protocol(socketserver.StreamRequestHandler):
        def handle(self):
            for raw in self.rfile:
                try:
                    line=raw.decode().strip();parts=shlex.split(line)
                    if not parts:continue
                    command=parts[0]
                    if command in ('USERNAME','PASSWORD'):reply='OK'
                    elif command=='LOGIN':state['logins']+=1;reply='OK'
                    elif command=='LOGOUT':self.wfile.write(b'OK Goodbye\n');return
                    elif command=='GET' and parts[1:]==['VAR','test','ups.status']:
                        state['gets']+=1;reply='VAR test ups.status "'+state['status']+'"'
                    elif command=='GET' and parts[1:]==['VAR','test','ups.description']:
                        reply='VAR test ups.description "Isolated validation UPS"'
                    elif command=='VER':reply='Network UPS Tools upsd 2.8.0'
                    else:reply='ERR FEATURE-NOT-SUPPORTED'
                    self.wfile.write((reply+'\n').encode());self.wfile.flush()
                except (OSError,ValueError):return
    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address=True;daemon_threads=True
    with tempfile.TemporaryDirectory(prefix='isolated-nut-') as directory,Server(('127.0.0.1',0),Protocol) as server:
        directory=Path(directory);marker=directory/'shutdown-marker'
        action='/usr/local/sbin/nas-ups-shutdown --validation' if real else '/usr/bin/touch '+str(marker)
        user='nut' if privsep else pwd.getpwuid(os.geteuid()).pw_name
        config=f'''MONITOR test@127.0.0.1:{server.server_address[1]} 1 test test secondary
MINSUPPLIES 1
SHUTDOWNCMD "{action}"
POWERDOWNFLAG {directory}/powerdown
POLLFREQ 1
POLLFREQALERT 1
HOSTSYNC 1
DEADTIME 5
FINALDELAY 0
RUN_AS_USER {user}
'''
        (directory/'upsmon.conf').write_text(config)
        statepath=directory/'state';statepath.mkdir()
        if privsep:
            gid=grp.getgrnam('nut').gr_gid;uid=pwd.getpwnam('nut').pw_uid
            os.chown(directory,0,gid);directory.chmod(0o750)
            os.chown(directory/'upsmon.conf',0,gid);(directory/'upsmon.conf').chmod(0o640)
            os.chown(statepath,uid,gid);statepath.chmod(0o770)
        env={**os.environ,'NUT_CONFPATH':str(directory),'NUT_STATEPATH':str(statepath),'NUT_ALTPIDPATH':str(statepath)}
        threading.Thread(target=server.serve_forever,daemon=True).start()
        args=['/usr/lib/nut/upsmon','-F']+(['-u','nut'] if privsep else ['-p'])
        process=subprocess.Popen(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        try:
            deadline=time.monotonic()+12
            while state['gets']<2 and process.poll() is None and time.monotonic()<deadline:time.sleep(.2)
            if state['gets']<2:raise RuntimeError('Client did not poll isolated UPS')
            if marker.exists():raise RuntimeError('Unexpected action during OL')
            print('PASS: OL monitored without shutdown',flush=True)
            state['status']='OB'
            baseline=state['gets'];deadline=time.monotonic()+5
            while state['gets']<baseline+2 and time.monotonic()<deadline:time.sleep(.2)
            if marker.exists():raise RuntimeError('Unexpected shutdown during OB only')
            print('PASS: OB alone does not shut down',flush=True)
            state['status']='OB LB FSD'
            if real:print('Real validation: critical synthetic UPS will now power off NAS',flush=True)
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                if not real and marker.exists():
                    print('PASS: critical state executes configured harmless action',flush=True)
                    return True
                if real and Path('/var/lib/nas-nut-client/last-shutdown.json').exists():
                    record=json.loads(Path('/var/lib/nas-nut-client/last-shutdown.json').read_text())
                    if record.get('origin')=='validation' and time.time()-record['at']<30:return True
                if process.poll() is not None:break
                time.sleep(.2)
            raise RuntimeError('Critical state did not execute shutdown action')
        except Exception:
            process.terminate()
            output=process.communicate(timeout=5)[0]
            print(output[-3500:]) # isolated config contains only test/test credentials
            raise
        finally:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            if process.stdout:process.stdout.close()
            server.shutdown()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real-poweroff',action='store_true')
    parser.add_argument('--privsep',action='store_true',help='Root: harmless test using production privilege separation')
    args=parser.parse_args()
    run_test(args.real_poweroff,args.privsep)
