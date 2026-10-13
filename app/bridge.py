"""Windows WASAPI -> live MP3 -> Bose SoundTouch UPnP, local network only."""
import argparse
import array
import ctypes
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import queue
import secrets
import socket
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import lameenc
import pyaudiowpatch as pa

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
ASSETS = DATA / 'assets'
for directory in (DATA / 'logs', ASSETS, DATA / 'reports'):
    directory.mkdir(parents=True, exist_ok=True)
CONFIG = DATA / 'config.json'
if not CONFIG.exists() and (ROOT / 'config.json').exists():
    (ROOT / 'config.json').replace(CONFIG)
LOG = logging.getLogger('quartos')
LOG.setLevel(logging.INFO)
handler = RotatingFileHandler(DATA / 'logs' / 'bridge.log', maxBytes=1_000_000, backupCount=3, encoding='utf-8')
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
LOG.addHandler(handler)


def request(url, body=None, headers=None):
    req = urllib.request.Request(url, data=body.encode('utf-8') if body is not None else None,
                                 headers=headers or {})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.read().decode('utf-8')


class Bridge:
    def __init__(self):
        self.cfg = json.loads(CONFIG.read_text('utf-8'))
        self.ip = self.cfg['speaker_ip']
        self.enabled = self.cfg.get('enabled', True)
        self.stop = threading.Event()
        self.reconnect = threading.Event()
        self.reconnect.set()
        self.clients = set()
        self.lock = threading.Lock()
        self.status = 'A iniciar…'
        self.capture_name = ''
        self.captured_frames = 0
        self.encoded_bytes = 0
        self.served_bytes = 0
        self.level = 0
        self.test_until = 0
        self.last_client = 0
        self.connected_once = False
        self.token = secrets.token_urlsafe(24)
        self.control_lock = threading.Lock()
        self.output_active = None
        self.pc_volume = None
        self.speaker_volume = None
        self.capture_drops = 0
        self.capture_flags = 0
        self.silent_fills = 0
        self.icon = None
        self.ui_show = threading.Event()
        self.workers = []

    def save(self):
        self.cfg['enabled'] = self.enabled
        target = CONFIG.with_suffix('.tmp')
        target.write_text(json.dumps(self.cfg, indent=2), 'utf-8')
        target.replace(CONFIG)

    @property
    def speaker_name(self):
        return self.cfg['speaker_name']

    def select_speaker(self, name):
        with self.control_lock:
            selected = self.cfg['speakers'][name]
            if selected['id'] != self.cfg['speaker_id']:
                if self.clients:
                    try:
                        np = ET.fromstring(request(f'http://{self.ip}:8090/now_playing'))
                        if np.get('source') == 'UPNP':
                            self.soap('Stop', {'InstanceID': 0})
                    except Exception:
                        LOG.exception('Parar coluna anterior')
                with self.lock:
                    for client in self.clients:
                        while not client.empty():
                            client.get_nowait()
                        client.put_nowait(None)
                    self.clients.clear()
                self.token = secrets.token_urlsafe(24)
                self.ip = self.cfg['speaker_ip'] = selected['ip']
                self.cfg['speaker_id'] = selected['id']
                self.cfg['speaker_name'] = name
                self.pc_volume = self.speaker_volume = None
                self.status = f'A ligar a {name}…'
            self.enabled = True
            self.reconnect.set()
            self.save()
        self.route(True)

    def soap(self, action, args):
        inner = ''.join(f'<{k}>{escape(str(v))}</{k}>' for k, v in args.items())
        xml = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
               's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
               f'<u:{action} xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">{inner}'
               f'</u:{action}></s:Body></s:Envelope>')
        return request(f'http://{self.ip}:8091/AVTransport/Control', xml, {
            'Content-Type': 'text/xml; charset="utf-8"',
            'SOAPAction': f'"urn:schemas-upnp-org:service:AVTransport:1#{action}"'})

    def local_ip(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((self.ip, 8090))
            return s.getsockname()[0]

    def connect(self):
        info = ET.fromstring(request(f'http://{self.ip}:8090/info'))
        if info.get('deviceID') != self.cfg['speaker_id']:
            raise RuntimeError(f'O endereço não pertence à coluna {self.speaker_name}.')
        zone = ET.fromstring(request(f'http://{self.ip}:8090/getZone'))
        if zone.get('master') and zone.get('master') != self.cfg['speaker_id']:
            raise RuntimeError(f'{self.speaker_name} está num grupo. Desagrupe na app SoundTouch para ligar ao PC.')
        url = f'http://{self.local_ip()}:{self.cfg["port"]}/audio/{self.token}.mp3'
        metadata = ('<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
                    'xmlns:dc="http://purl.org/dc/elements/1.1/" '
                    'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
                    f'<item id="pc" parentID="0" restricted="1"><dc:title>Áudio do PC — {escape(self.speaker_name)}</dc:title>'
                    '<upnp:class>object.item.audioItem.audioBroadcast</upnp:class>'
                    f'<res protocolInfo="http-get:*:audio/mpeg:*">{escape(url)}</res></item></DIDL-Lite>')
        self.soap('SetAVTransportURI', {'InstanceID': 0, 'CurrentURI': url, 'CurrentURIMetaData': metadata})
        self.soap('Play', {'InstanceID': 0, 'Speed': 1})
        self.connected_once = True
        LOG.info('UPnP Play: %s -> %s', self.local_ip(), self.ip)

    def broadcast(self, data):
        if not data:
            return
        self.encoded_bytes += len(data)
        with self.lock:
            for q in tuple(self.clients):
                try:
                    q.put_nowait(data)
                except queue.Full:
                    # A slow listener must reconnect rather than accumulate seconds of stale audio.
                    self.clients.discard(q)
                    while not q.empty():
                        q.get_nowait()
                    q.put_nowait(None)

    def capture(self):
        import comtypes
        from pycaw.pycaw import AudioUtilities
        comtypes.CoInitialize()
        while not self.stop.is_set():
            try:
                endpoint_id = AudioUtilities.GetSpeakers().id
                with pa.PyAudio() as audio:
                    dev = audio.get_default_wasapi_loopback()
                    self.capture_name = dev['name']
                    rate, channels = int(dev['defaultSampleRate']), dev['maxInputChannels']
                    if channels not in (1, 2):
                        raise RuntimeError('Defina a saída Windows como estéreo (2 canais).')
                    frames = rate // 50
                    packets = queue.Queue(maxsize=10)

                    def callback(data, count, timing, flags):
                        self.captured_frames += count
                        if flags:
                            self.capture_flags += 1
                        try:
                            packets.put_nowait(data)
                        except queue.Full:
                            self.capture_drops += 1
                            try:
                                packets.get_nowait()
                                packets.put_nowait(data)
                            except (queue.Empty, queue.Full):
                                pass
                        return (None, pa.paContinue)

                    encoder = lameenc.Encoder()
                    encoder.set_bit_rate(320)
                    encoder.set_in_sample_rate(rate)
                    encoder.set_channels(channels)
                    encoder.set_quality(2)
                    encoder.silence()
                    LOG.info('Captura: %s, %s Hz, %s canais', dev['name'], rate, channels)
                    with audio.open(format=pa.paInt16, channels=channels, rate=rate, input=True,
                                    input_device_index=dev['index'], frames_per_buffer=frames,
                                    stream_callback=callback) as stream:
                        check = time.monotonic() + 1
                        while not self.stop.is_set() and stream.is_active():
                            try:
                                # Follow the audio device clock. Polling a second clock and
                                # inserting silence on every empty poll caused gaps and drift.
                                pcm = packets.get(timeout=0.1)
                            except queue.Empty:
                                self.silent_fills += 1
                                pcm = bytes((rate // 10) * channels * 2)
                            if time.monotonic() < self.test_until:
                                import math
                                pcm = array.array('h', (int(900 * math.sin(2 * math.pi * 440 * i / rate))
                                                      for i in range(frames) for _ in range(channels))).tobytes()
                            values = array.array('h', pcm)
                            self.level = max((abs(x) for x in values), default=0) / 32768
                            self.broadcast(encoder.encode(pcm))
                            if time.monotonic() >= check:
                                check = time.monotonic() + 1
                                # PortAudio's device table is cached until every instance closes.
                                if AudioUtilities.GetSpeakers().id != endpoint_id:
                                    break
                        self.broadcast(encoder.flush())
            except Exception:
                LOG.exception('Captura indisponível; tentar novamente')
                self.capture_name = 'Sem saída de áudio disponível'
                self.stop.wait(5)
        comtypes.CoUninitialize()

    def discover(self):
        # SSDP resolves this exact device if its DHCP address changed.
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(1)
                s.sendto(b'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n'
                         b'MAN: "ssdp:discover"\r\nMX: 1\r\nST: ssdp:all\r\n\r\n',
                         ('239.255.255.250', 1900))
                end = time.monotonic() + 3
                found = set()
                while time.monotonic() < end:
                    try:
                        _, addr = s.recvfrom(8192)
                        found.add(addr[0])
                    except socket.timeout:
                        break
            for ip in found:
                try:
                    info = ET.fromstring(request(f'http://{ip}:8090/info'))
                    if info.get('deviceID') == self.cfg['speaker_id']:
                        self.ip = self.cfg['speaker_ip'] = ip
                        self.save()
                        return
                except Exception:
                    pass
        except Exception:
            LOG.exception('Descoberta SSDP')

    def monitor(self):
        failures = 0
        while not self.stop.is_set():
            try:
                with self.control_lock:
                    if self.output_active is None:
                        self.status = 'A preparar saída de áudio…'
                    elif not self.output_active:
                        self.status = f'{self.speaker_name} disponível — seleciona SoundTouch no Windows'
                        if self.clients:
                            np = ET.fromstring(request(f'http://{self.ip}:8090/now_playing'))
                            if np.get('source') == 'UPNP':
                                self.soap('Stop', {'InstanceID': 0})
                    elif self.enabled:
                        np = ET.fromstring(request(f'http://{self.ip}:8090/now_playing'))
                        with self.lock:
                            listening = bool(self.clients)
                        force = self.reconnect.is_set()
                        if force or (not listening and np.get('source') in ('UPNP', 'STANDBY', 'INVALID_SOURCE')):
                            self.connect()
                            self.reconnect.clear()
                            self.status = f'{self.speaker_name} · ligado' if self.clients else f'A ligar a {self.speaker_name}…'
                        elif listening:
                            self.status = f'{self.speaker_name} · ligado'
                        else:
                            self.status = f'{self.speaker_name} noutra fonte — restabelece a ligação para retomar'
                    else:
                        self.status = 'Ponte em pausa'
                failures = 0
            except Exception as e:
                failures += 1
                self.status = f'A aguardar {self.speaker_name}: {e}'
                LOG.warning('%s', self.status)
                if failures % 3 == 0:
                    self.discover()
            if self.icon:
                self.icon.title = self.status[:127]
                self.icon.update_menu()
            self.stop.wait(1.5)

    def volume_sync(self):
        """The Windows slider controls Bose volume; hardware changes update the slider."""
        import comtypes
        from pycaw.pycaw import AudioUtilities
        comtypes.CoInitialize()
        device_id = None
        endpoint = None
        previous = None
        last_poll = 0
        volume_speaker = None
        while not self.stop.is_set():
            try:
                raw = AudioUtilities.GetDeviceEnumerator().GetDefaultAudioEndpoint(0, 1)
                current_id = raw.GetId()
                if current_id != device_id:
                    device = AudioUtilities.CreateDevice(raw)
                    device_id = current_id
                    endpoint = device.EndpointVolume
                    was_active = self.output_active
                    self.output_active = device.FriendlyName.startswith('SoundTouch')
                    previous = None
                    if self.output_active and was_active is False:
                        self.enable()
                if not (self.output_active and self.enabled and self.clients):
                    previous = None
                    self.stop.wait(0.25)
                    continue
                if volume_speaker != self.ip:
                    volume_speaker = self.ip
                    previous = None
                state = (round(endpoint.GetMasterVolumeLevelScalar() * 100), bool(endpoint.GetMute()))
                now = time.monotonic()
                if previous is None or state != previous or now - last_poll >= 1:
                    with self.control_lock:
                        if volume_speaker != self.ip:
                            previous = None
                            continue
                        xml = ET.fromstring(request(f'http://{self.ip}:8090/volume'))
                        actual = (int(xml.findtext('actualvolume', '0')), xml.findtext('muteenabled') == 'true')
                        if previous is not None and state != previous:
                            if state[0] != actual[0]:
                                request(f'http://{self.ip}:8090/volume', f'<volume>{state[0]}</volume>', {'Content-Type': 'text/xml'})
                            if state[1] != actual[1]:
                                for key_state in ('press', 'release'):
                                    request(f'http://{self.ip}:8090/key', f'<key state="{key_state}" sender="PC">MUTE</key>', {'Content-Type': 'text/xml'})
                            self.speaker_volume = state[0]
                            LOG.info('Volume Windows -> %s: %s, mute=%s', self.speaker_name, *state)
                        else:
                            # Preserve the selected speaker's loudness on connection.
                            if state[0] != actual[0]:
                                endpoint.SetMasterVolumeLevelScalar(actual[0] / 100, None)
                            if state[1] != actual[1]:
                                endpoint.SetMute(actual[1], None)
                            state = actual
                            self.speaker_volume = actual[0]
                        previous = state
                        self.pc_volume = state[0]
                        last_poll = time.monotonic()
            except Exception:
                LOG.exception('Sincronização de volume')
                previous = None
                self.stop.wait(2)
            self.stop.wait(0.25)
        comtypes.CoUninitialize()

    def enable(self):
        with self.control_lock:
            self.enabled = True
            self.reconnect.set()
            self.save()

    def pause(self):
        with self.control_lock:
            self.enabled = False
            self.save()
            try:
                np = ET.fromstring(request(f'http://{self.ip}:8090/now_playing'))
                if np.get('source') == 'UPNP' and self.clients:
                    self.soap('Stop', {'InstanceID': 0})
            except Exception:
                LOG.exception('Parar UPnP')

    def route(self, to_speaker=True):
        import comtypes
        from pycaw.pycaw import AudioUtilities
        from pycaw.constants import ERole
        comtypes.CoInitialize()
        try:
            current = AudioUtilities.GetSpeakers().id
            devices = AudioUtilities.GetAllDevices()
            cable = next((d for d in devices if d.id.startswith('{0.0.0.') and d.state.value == 1
                          and d.FriendlyName.startswith('SoundTouch')), None)
            if to_speaker:
                if not cable:
                    raise RuntimeError('Instale o VB-CABLE e reinicie o PC para aparecer a saída SoundTouch.')
                if current != cable.id:
                    self.cfg['previous_output'] = current
                    self.save()
                target = cable.id
            else:
                target = self.cfg.get('previous_output')
                if not target or not any(d.id == target and d.state.value == 1 for d in devices):
                    raise RuntimeError('A saída anterior não está disponível. Escolha outra nas definições de som.')
            AudioUtilities.SetDefaultDevice(target, [ERole.eConsole, ERole.eMultimedia])
            if to_speaker:
                self.enable()
            else:
                self.pause()
        finally:
            comtypes.CoUninitialize()

    def snapshot(self):
        return {'status': self.status, 'enabled': self.enabled, 'speaker_ip': self.ip,
                'speaker_name': self.speaker_name,
                'capture': self.capture_name, 'clients': len(self.clients),
                'captured_frames': self.captured_frames, 'encoded_bytes': self.encoded_bytes,
                'served_bytes': self.served_bytes, 'level': round(self.level, 4),
                'pc_volume': self.pc_volume, 'speaker_volume': self.speaker_volume,
                'output_active': self.output_active, 'bitrate_kbps': 320,
                'capture_drops': self.capture_drops, 'capture_flags': self.capture_flags,
                'silent_fills': self.silent_fills}

    def serve(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.0'

            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path == '/status' and self.client_address[0] == '127.0.0.1':
                    data = json.dumps(bridge.snapshot(), ensure_ascii=False).encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                if self.path != f'/audio/{bridge.token}.mp3' or self.client_address[0] not in (bridge.ip, '127.0.0.1'):
                    self.send_error(404)
                    return
                self.connection.settimeout(8)
                q = queue.Queue(maxsize=75)
                self.send_response(200)
                self.send_header('Content-Type', 'audio/mpeg')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Accept-Ranges', 'none')
                self.send_header('transferMode.dlna.org', 'Streaming')
                self.send_header('Connection', 'close')
                self.end_headers()
                with bridge.lock:
                    bridge.clients.add(q)
                LOG.info('Coluna abriu stream: %s', self.client_address[0])
                try:
                    while not bridge.stop.is_set():
                        data = q.get(timeout=8)
                        if data is None:
                            break
                        self.wfile.write(data)
                        self.wfile.flush()
                        bridge.served_bytes += len(data)
                except (OSError, queue.Empty):
                    pass
                finally:
                    with bridge.lock:
                        bridge.clients.discard(q)
                    LOG.info('Stream fechado: %s', self.client_address[0])

        self.server = ThreadingHTTPServer(('0.0.0.0', self.cfg['port']), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        for function in (self.capture, self.volume_sync, self.monitor):
            worker = threading.Thread(target=function, daemon=True)
            self.workers.append(worker)
            worker.start()

    def shutdown(self):
        self.stop.set()
        self.server.shutdown()
        for worker in self.workers:
            worker.join(timeout=6)

    def panel(self):
        import tkinter as tk
        import comtypes
        from pycaw.pycaw import AudioUtilities
        comtypes.CoInitialize()
        root = tk.Tk()
        root.title('SoundTouch · Áudio do PC')
        if (ASSETS / 'soundtouch.ico').exists():
            root.iconbitmap(str(ASSETS / 'soundtouch.ico'))
        root.geometry('540x510')
        root.resizable(False, False)
        root.configure(bg='#101820')
        root.withdraw()
        root.protocol('WM_DELETE_WINDOW', root.withdraw)
        bg, card, fg, dim, accent = '#101820', '#1b2935', '#f1f6fa', '#9aafbf', '#57dfbc'
        heading = tk.Frame(root, bg=bg)
        heading.pack(fill='x', padx=30, pady=(27, 20))
        tk.Label(heading, text='SoundTouch', font=('Segoe UI', 25, 'bold'), fg=fg, bg=bg).pack(anchor='w')
        tk.Label(heading, text='O som do teu PC, nas tuas colunas.', font=('Segoe UI', 11), fg=dim, bg=bg).pack(anchor='w', pady=(3, 0))
        connection = tk.Frame(root, bg=card, padx=20, pady=17)
        connection.pack(fill='x', padx=30)
        status_label = tk.Label(connection, text='A verificar ligação…', font=('Segoe UI', 12, 'bold'), fg=accent, bg=card)
        status_label.pack(anchor='w')
        info_label = tk.Label(connection, text='SoundTouch SA-5 · Wi-Fi', font=('Segoe UI', 10), fg=dim, bg=card)
        info_label.pack(anchor='w', pady=(4, 0))
        tk.Label(root, text='ONDE QUERES OUVIR?', font=('Segoe UI', 9, 'bold'), fg=dim, bg=bg).pack(anchor='w', padx=30, pady=(22, 9))
        choices = tk.Frame(root, bg=bg)
        choices.pack(fill='x', padx=30)
        message = tk.StringVar()

        def work(fn):
            def run():
                try:
                    fn()
                except Exception as e:
                    LOG.exception('Painel')
                    errors.put(str(e))
            threading.Thread(target=run, daemon=True).start()

        errors = queue.Queue()
        left = tk.Button(choices, text='♫  Quartos', font=('Segoe UI', 12, 'bold'), relief='flat', bd=0,
                         padx=10, pady=11, cursor='hand2', command=lambda: work(lambda: self.select_speaker('Quartos')))
        left.pack(side='left', fill='x', expand=True, padx=(0, 6))
        sala = tk.Button(choices, text='♫  Sala', font=('Segoe UI', 12, 'bold'), relief='flat', bd=0,
                         padx=10, pady=11, cursor='hand2', command=lambda: work(lambda: self.select_speaker('Sala')))
        sala.pack(side='left', fill='x', expand=True, padx=(0, 6))
        right = tk.Button(choices, text='▣  Este PC', font=('Segoe UI', 12, 'bold'), relief='flat', bd=0,
                          padx=10, pady=11, cursor='hand2', command=lambda: work(lambda: self.route(False)))
        right.pack(side='left', fill='x', expand=True)
        volume_header = tk.Frame(root, bg=bg)
        volume_header.pack(fill='x', padx=30, pady=(22, 0))
        volume_title = tk.Label(volume_header, text='Volume da coluna', font=('Segoe UI', 11), fg=fg, bg=bg)
        volume_title.pack(side='left')
        volume_label = tk.Label(volume_header, text='—', font=('Segoe UI', 14, 'bold'), fg=accent, bg=bg)
        volume_label.pack(side='right')
        cable_endpoint = None

        def cable_volume():
            nonlocal cable_endpoint
            if cable_endpoint is None:
                cable = next(d for d in AudioUtilities.GetAllDevices() if d.id.startswith('{0.0.0.')
                             and d.state.value == 1 and d.FriendlyName.startswith('SoundTouch'))
                cable_endpoint = cable.EndpointVolume
            return cable_endpoint

        def change_volume(value):
            try:
                endpoint = cable_volume()
                number = int(float(value))
                if number != round(endpoint.GetMasterVolumeLevelScalar() * 100):
                    endpoint.SetMasterVolumeLevelScalar(number / 100, None)
                volume_label.configure(text=str(number))
            except Exception as e:
                message.set(str(e))

        slider = tk.Scale(root, from_=0, to=100, orient='horizontal', showvalue=False, command=change_volume,
                          bg=bg, fg=fg, troughcolor=card, activebackground=accent, highlightthickness=0,
                          bd=0, sliderrelief='flat', sliderlength=18, width=8)
        slider.pack(fill='x', padx=28, pady=(9, 0))
        hint = tk.Label(root, text='Também podes usar o volume do Windows ou as teclas do teclado.',
                        font=('Segoe UI', 9), fg=dim, bg=bg)
        hint.pack(anchor='w', padx=30, pady=(8, 0))
        footer = tk.Frame(root, bg=bg)
        footer.pack(fill='x', padx=30, pady=(20, 0))
        tk.Button(footer, text='Usar Spotify', command=lambda: work(self.pause), bg=card, fg=fg,
                  font=('Segoe UI', 10), relief='flat', padx=13, pady=7, cursor='hand2').pack(side='left')
        tk.Button(footer, text='Restabelecer ligação', command=lambda: work(self.enable), bg=bg, fg=dim,
                  font=('Segoe UI', 10), relief='flat', padx=10, pady=7, cursor='hand2').pack(side='right')
        tk.Label(root, textvariable=message, font=('Segoe UI', 9), fg='#f8b98a', bg=bg,
                 wraplength=480).pack(anchor='w', padx=30, pady=5)

        def update():
            if self.stop.is_set():
                root.destroy()
                return
            if self.ui_show.is_set():
                self.ui_show.clear()
                root.deiconify()
                root.lift()
            if not errors.empty():
                message.set(errors.get_nowait())
            active = self.output_active and self.enabled
            status_label.configure(text=(f'●  {self.speaker_name} · ligado' if active and self.clients else
                                         f'●  {self.speaker_name} livre para Spotify' if not self.enabled and self.output_active else
                                         '●  A ouvir neste PC' if self.output_active is False else f'●  A ligar a {self.speaker_name}…'),
                                   fg=accent if active and self.clients else dim)
            info_label.configure(text=f'Bose {self.cfg["speakers"][self.speaker_name]["model"]} · Wi-Fi')
            volume_title.configure(text=f'Volume · {self.speaker_name}')
            quart_active = active and self.speaker_name == 'Quartos'
            sala_active = active and self.speaker_name == 'Sala'
            left.configure(bg=accent if quart_active else card, fg=bg if quart_active else fg,
                           activebackground=accent, activeforeground=bg)
            sala.configure(bg=accent if sala_active else card, fg=bg if sala_active else fg,
                           activebackground=accent, activeforeground=bg)
            right.configure(bg=accent if not self.output_active else card, fg=bg if not self.output_active else fg,
                            activebackground=accent, activeforeground=bg)
            slider.configure(state='normal' if active and self.clients else 'disabled')
            try:
                current = round(cable_volume().GetMasterVolumeLevelScalar() * 100)
                if int(slider.get()) != current:
                    slider.set(current)
                volume_label.configure(text=str(current))
            except Exception:
                pass
            root.after(250, update)

        update()
        root.mainloop()
        comtypes.CoUninitialize()

    def tray(self):
        import pystray
        from PIL import Image, ImageDraw
        icon_image = Image.new('RGB', (64, 64), '#163e50')
        draw = ImageDraw.Draw(icon_image)
        draw.rounded_rectangle((16, 8, 48, 56), radius=7, fill='#39d5ac')
        draw.ellipse((24, 28, 40, 44), fill='#163e50')
        draw.ellipse((28, 16, 36, 24), fill='#163e50')
        icon_image.save(ASSETS / 'soundtouch.ico', sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])

        def action(fn):
            def run(icon, item):
                def work():
                    try:
                        fn()
                    except Exception as e:
                        LOG.exception('Ação')
                        icon.notify(str(e), 'SoundTouch Quartos')
                threading.Thread(target=work, daemon=True).start()
            return run

        def quit_app(icon, item):
            try:
                wanted_enabled = self.enabled
                self.route(False)
                self.enabled = wanted_enabled
                self.save()
            except Exception:
                LOG.exception('Restaurar saída ao sair')
            self.shutdown()
            icon.stop()

        menu = pystray.Menu(
            pystray.MenuItem('Abrir SoundTouch', action(self.ui_show.set), default=True),
            pystray.MenuItem('Sair', quit_app))
        icon = pystray.Icon('SoundTouchQuartos', icon_image, 'SoundTouch Quartos', menu)
        self.icon = icon
        threading.Thread(target=self.panel, daemon=True).start()
        icon.run()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--route', choices=['quartos', 'pc'])
    parser.add_argument('--panel', action='store_true')
    args = parser.parse_args()
    if args.route:
        Bridge().route(args.route == 'quartos')
        return
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, 'Local\\SoundTouchQuartosBridge')
    if ctypes.windll.kernel32.GetLastError() == 183:
        return
    try:
        bridge = Bridge()
        if args.panel:
            bridge.ui_show.set()
        bridge.serve()
        LOG.info('Ponte iniciada')
        if args.headless:
            while not bridge.stop.wait(1):
                pass
        else:
            bridge.tray()
    except Exception:
        LOG.exception('Falha na app')
        raise
    finally:
        ctypes.windll.kernel32.CloseHandle(mutex)


if __name__ == '__main__':
    main()
