#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ "$(id -u)" = 0 ] || { echo 'Execute com sudo.'; exit 1; }
if systemctl is-active --quiet nas-nut-client.service; then
    echo 'Cliente dedicado já ativo. Para corrigir a validação, use fix-validation.sh.'; exit 1
fi
# Re-run harmless integration before changing any service.
python3 -B isolated_nut_test.py
python3 -B isolated_nut_test.py --privsep
for service in nut-monitor ups-monitor; do
    if systemctl is-active --quiet "$service"; then echo "Outro cliente ativo: $service. Revisar antes de prosseguir."; exit 1; fi
done
python3 -B - <<'PYINSTALL'
import socket,json,time,shutil,os,pwd,grp
from pathlib import Path
credential=json.loads(Path('credential.json').read_text())
def quote(value):return '"'+value.replace('\\','\\\\').replace('"','\\"')+'"'
with socket.create_connection(('192.168.50.143',3493),timeout=5) as sock:
    stream=sock.makefile('rwb',buffering=0)
    def command(text):stream.write((text+'\n').encode());return stream.readline().decode().strip()
    state=command('GET VAR ragtech ups.status')
    if '"OL"' not in state:raise SystemExit('UPS não está em OL normal; ativação cancelada')
    for command_text in ['USERNAME upsmon_nas','PASSWORD '+credential['password'],'LOGIN ragtech']:
        if command(command_text)!='OK':raise SystemExit('Autenticação NUT falhou; ativação cancelada')
    command('LOGOUT')
backup=Path('/var/backups')/('nas-nut-client-'+str(int(time.time())))
backup.mkdir(mode=0o700)
for source in ['/etc/nut/nut.conf','/etc/nut/upsmon.conf','/etc/systemd/system/nas-nut-client.service']:
    p=Path(source)
    if p.exists():shutil.copy2(p,backup/p.name)
profile=Path('/etc/nas-nut-client');profile.mkdir(mode=0o750,exist_ok=True)
gid=grp.getgrnam('nut').gr_gid;os.chown(profile,0,gid);profile.chmod(0o750)
config='\n'.join([
    'MONITOR ragtech@192.168.50.143 1 upsmon_nas '+quote(credential['password'])+' secondary',
    'MINSUPPLIES 1','SHUTDOWNCMD "/usr/local/sbin/nas-ups-shutdown"',
    'POLLFREQ 5','POLLFREQALERT 5','HOSTSYNC 15','DEADTIME 15','FINALDELAY 5',
    'POWERDOWNFLAG /run/nas-nut-client/killpower','RUN_AS_USER nut','SHUTDOWNEXIT yes',''])
(profile/'upsmon.conf').write_text(config)
(profile/'nut.conf').write_text('MODE=netclient\n')
for p in profile.iterdir():os.chown(p,0,gid);p.chmod(0o640)
print('Login NAS→Pi validado; backup:',backup)
PYINSTALL
install -d -m 755 /opt/nas-nut-client /var/lib/nas-nut-client
install -m 755 nas-ups-shutdown /usr/local/sbin/nas-ups-shutdown
install -m 644 isolated_nut_test.py validation_guard.py /opt/nas-nut-client/
install -m 644 nas-nut-client.service nas-nut-validation.service /etc/systemd/system/
systemd-analyze verify /etc/systemd/system/nas-nut-client.service /etc/systemd/system/nas-nut-validation.service
# A single authorized real validation can be initiated remotely without exposing sudo credentials.
fragment=$(mktemp)
printf '%s\n' 'cleibersilva ALL=(root) NOPASSWD: /usr/bin/systemctl start --no-block nas-nut-validation.service' > "$fragment"
visudo -cf "$fragment"
install -m 440 "$fragment" /etc/sudoers.d/nas-nut-validation
unlink "$fragment"
# Do not enable the UGOS wrapper or a second daemon alongside the dedicated client.
systemctl disable nut-monitor.service
/sbin/ethtool -s eth0 wol g
# Persist WOL at boot, scoped only to this interface.
printf '%s\n' '[Unit]' 'Description=Enable NAS Wake-on-LAN' 'After=network.target' '[Service]' 'Type=oneshot' 'ExecStart=/sbin/ethtool -s eth0 wol g' 'RemainAfterExit=yes' '[Install]' 'WantedBy=multi-user.target' > /etc/systemd/system/nas-nut-wol.service
systemctl daemon-reload
systemctl enable --now nas-nut-wol.service nas-nut-client.service
sleep 8
systemctl is-active nas-nut-client.service
printf '%s\n' 'Cliente NAS instalado e ativo. Nenhum desligamento real executado. Validação real será iniciada separadamente após programar WOL no Raspberry.'
