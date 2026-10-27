#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ "$(id -u)" = 0 ] || { echo 'Execute com sudo.'; exit 1; }
python3 -B -m unittest discover -s tests -v
python3 -B - <<'PYINSTALL'
import ast
from pathlib import Path
ast.parse(Path('macmini-power-control').read_text())
pub=Path('raspberry-power.pub').read_text().strip()
assert pub.startswith('ssh-ed25519 ') and len(pub.split())==3
PYINSTALL
sh -n macmini-power-ssh
install -d -m 755 /usr/local/libexec
install -m 755 macmini-power-control /usr/local/libexec/macmini-power-control
install -m 755 macmini-power-ssh /usr/local/libexec/macmini-power-ssh
sudoers=$(mktemp)
printf '%s\n' 'cleiber ALL=(root) NOPASSWD: /usr/local/libexec/macmini-power-control status, /usr/local/libexec/macmini-power-control suspend' > "$sudoers"
visudo -cf "$sudoers"
install -m 440 "$sudoers" /etc/sudoers.d/macmini-ups-power
# Only the generated temporary sudoers fragment is removed.
unlink "$sudoers"
python3 -B - <<'PYINSTALL'
from pathlib import Path
import os,pwd,shutil,time
user=pwd.getpwnam('cleiber');ssh=Path(user.pw_dir)/'.ssh';ssh.mkdir(mode=0o700,exist_ok=True)
authorized=ssh/'authorized_keys'
if authorized.exists():shutil.copy2(authorized,ssh/('authorized_keys.before-ups-'+str(int(time.time()))))
public=Path('raspberry-power.pub').read_text().strip()
line='restrict,from="192.168.50.143",command="/usr/local/libexec/macmini-power-ssh" '+public
existing=authorized.read_text() if authorized.exists() else ''
if public.split()[1] not in existing:
    authorized.write_text(existing.rstrip()+'\n'+line+'\n')
os.chown(ssh,user.pw_uid,user.pw_gid);os.chown(authorized,user.pw_uid,user.pw_gid);authorized.chmod(0o600)
PYINSTALL
nmcli connection modify 'Conexão cabeada 1' 802-3-ethernet.wake-on-lan magic
ethtool -s enp3s0f0 wol g
if [ -f /sys/class/net/enp3s0f0/device/power/wakeup ]; then
    printf '%s' enabled > /sys/class/net/enp3s0f0/device/power/wakeup
fi
/usr/local/libexec/macmini-power-control status
printf '%s\n' 'Instalado no Mac mini. Nenhuma suspensão executada.'
