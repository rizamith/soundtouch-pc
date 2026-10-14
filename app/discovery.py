"""Read-only discovery of Bose SoundTouch units on the selected local network."""
from concurrent.futures import ThreadPoolExecutor
import ipaddress
import socket
import time
import urllib.request
import xml.etree.ElementTree as ET
import psutil


def local_network(local_ip):
    for addresses in psutil.net_if_addrs().values():
        for address in addresses:
            if address.family == socket.AF_INET and address.address == local_ip and address.netmask:
                return ipaddress.ip_network(f'{local_ip}/{address.netmask}', strict=False)
    return ipaddress.ip_network(f'{local_ip}/24', strict=False)


def probe(ip):
    try:
        with urllib.request.urlopen(f'http://{ip}:8090/info', timeout=0.8) as response:
            info = ET.fromstring(response.read())
        if info.tag != 'info' or not info.get('deviceID') or not info.findtext('name') or not info.findtext('type'):
            return None
        return {'name': info.findtext('name'), 'id': info.get('deviceID'),
                'ip': ip, 'model': info.findtext('type')}
    except (OSError, ValueError, ET.ParseError):
        return None


def scan(local_ip, known_ips=()):
    network = local_network(local_ip)
    candidates = {str(ip) for ip in known_ips if ipaddress.ip_address(ip) in network}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((local_ip, 0))
        sock.settimeout(0.3)
        sock.sendto(b'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n'
                    b'MAN: "ssdp:discover"\r\nMX: 1\r\nST: ssdp:all\r\n\r\n',
                    ('239.255.255.250', 1900))
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            try:
                _, address = sock.recvfrom(8192)
                if ipaddress.ip_address(address[0]) in network:
                    candidates.add(address[0])
            except socket.timeout:
                continue
    # Some SoundTouch firmware does not answer SSDP reliably. Limit the HTTP
    # fallback to the local /24 on large networks (at most 254 fallback hosts).
    fallback = network if network.prefixlen >= 24 else ipaddress.ip_network(f'{local_ip}/24', strict=False)
    candidates.update(str(ip) for ip in fallback.hosts() if str(ip) != local_ip)
    with ThreadPoolExecutor(max_workers=32) as pool:
        found = [speaker for speaker in pool.map(probe, sorted(candidates)) if speaker]
    unique = {speaker['id']: speaker for speaker in found}
    return sorted(unique.values(), key=lambda speaker: (speaker['name'].casefold(), speaker['id']))
