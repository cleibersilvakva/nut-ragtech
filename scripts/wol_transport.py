"""Send NAS magic packets over Ethernet; errors must reach the controller."""
import ipaddress
import json
from pathlib import Path
import re
import socket
import subprocess
import time


def send_magic(mac, interface='eth0', count=3):
    if not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', mac):
        raise ValueError('MAC inválido')
    if not re.fullmatch(r'[a-zA-Z0-9_.-]+', interface) or count != 3:
        raise ValueError('Interface ou quantidade inválida')
    if Path('/sys/class/net', interface, 'carrier').read_text().strip() != '1':
        raise RuntimeError('Ethernet sem link; WOL não enviado')
    result = subprocess.run(['ip', '-j', '-4', 'addr', 'show', 'dev', interface],
                            check=True, capture_output=True, text=True, timeout=5)
    addresses = [a for item in json.loads(result.stdout) for a in item['addr_info']
                 if a.get('family') == 'inet' and a.get('scope') == 'global']
    if len(addresses) != 1:
        raise RuntimeError('Ethernet precisa de um endereço IPv4 inequívoco')
    address = addresses[0]
    network = ipaddress.IPv4Interface(f"{address['local']}/{address['prefixlen']}")
    if not 1 <= network.network.prefixlen <= 30:
        raise ValueError('Rede sem broadcast utilizável')
    packet = b'\xff' * 6 + bytes.fromhex(mac.replace(':', '')) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode() + b'\0')
        sock.bind((str(network.ip), 0))
        for index in range(count):
            if sock.sendto(packet, (str(network.network.broadcast_address), 9)) != len(packet):
                raise OSError('Pacote WOL incompleto')
            if index < count - 1:
                time.sleep(1)
    return {'interface': interface, 'source': str(network.ip), 'packets': count}
