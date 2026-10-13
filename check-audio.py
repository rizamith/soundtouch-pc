"""Play a quiet six-second alternating tone and verify real WASAPI capture."""
import json
from pathlib import Path
import urllib.request
import wave
import pyaudiowpatch as pa

def status():
    with urllib.request.urlopen('http://127.0.0.1:18788/status', timeout=3) as r:
        return json.load(r)

before = status()
peak = 0
with pa.PyAudio() as audio:
    api = audio.get_host_api_info_by_type(pa.paWASAPI)
    device = audio.get_device_info_by_index(api['defaultOutputDevice'])
    print('Output:', device['name'])
    with wave.open(str(Path(__file__).with_name('test-tone.wav')), 'rb') as wav:
        with audio.open(format=pa.paInt16, channels=2, rate=48000, output=True,
                        output_device_index=device['index']) as stream:
            n = 0
            while data := wav.readframes(960):
                stream.write(data)
                n += 1
                if n % 10 == 0:
                    current = status()
                    peak = max(peak, current['level'])
                    if n % 50 == 0:
                        print(current)
after = status()
report = {'before': before, 'after': after, 'peak': peak,
          'capture_verified': after['captured_frames'] > before['captured_frames'] and peak > 0,
          'delivery_verified': after['served_bytes'] > before['served_bytes'] and after['clients'] > 0}
Path(__file__).with_name('audio-test.json').write_text(json.dumps(report, indent=2), 'utf-8')
print(json.dumps(report, indent=2))
assert report['capture_verified'], 'No actual audio captured'
assert report['delivery_verified'], 'Speaker did not receive stream'
