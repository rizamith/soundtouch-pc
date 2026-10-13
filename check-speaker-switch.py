"""Integration check: switch the running bridge between the two known Bose units."""
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET
from bridge import Bridge, request

bridge = Bridge()
initial = bridge.speaker_name
results = []
try:
    bridge.serve()
    for name in ('Sala', 'Quartos'):
        bridge.select_speaker(name)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            np = ET.fromstring(request(f'http://{bridge.ip}:8090/now_playing'))
            if bridge.clients and bridge.speaker_volume is not None and np.findtext('playStatus') == 'PLAY_STATE':
                break
            time.sleep(0.5)
        np = ET.fromstring(request(f'http://{bridge.ip}:8090/now_playing'))
        results.append({'speaker': name, 'ip': bridge.ip, 'clients': len(bridge.clients),
                        'source': np.get('source'), 'play_state': np.findtext('playStatus'),
                        'speaker_volume': bridge.speaker_volume, 'pc_volume': bridge.pc_volume})
        print(json.dumps(results[-1]))
        assert bridge.clients, f'{name} did not open the audio stream'
        assert np.get('source') == 'UPNP', f'{name} did not switch to UPnP'
        assert np.findtext('playStatus') == 'PLAY_STATE', f'{name} is not playing'
        assert bridge.pc_volume == bridge.speaker_volume, f'{name} volume not synchronized'
finally:
    if bridge.speaker_name != initial:
        bridge.select_speaker(initial)
        time.sleep(2)
    bridge.shutdown()
    Path(__file__).with_name('speaker-switch-test.json').write_text(json.dumps(results, indent=2), 'utf-8')
