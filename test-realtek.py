"""A direct WASAPI test of Realtek, independent of the SoundTouch bridge."""
import array
import json
import math
from pathlib import Path
import threading
import pyaudiowpatch as pa

samples = []
def capture(data, count, timing, flags):
    samples.append(max((abs(x) for x in array.array('h', data)), default=0))
    return None, pa.paContinue

with pa.PyAudio() as audio:
    api = audio.get_host_api_info_by_type(pa.paWASAPI)
    output = next(d for d in audio.get_device_info_generator()
                  if d['hostApi'] == api['index'] and d['maxOutputChannels'] > 0
                  and 'Realtek' in d['name'])
    loopback = audio.get_wasapi_loopback_analogue_by_dict(output)
    rate = int(output['defaultSampleRate'])
    channels = 2
    with audio.open(format=pa.paInt16, channels=channels, rate=rate,
                    input=True, input_device_index=loopback['index'],
                    frames_per_buffer=rate//50, stream_callback=capture):
        with audio.open(format=pa.paInt16, channels=channels, rate=rate,
                        output=True, output_device_index=output['index']) as stream:
            for second in range(6):
                frequency = 660 if second % 2 == 0 else 880
                for block in range(50):
                    signal = array.array('h', (int(4000 * math.sin(2*math.pi*frequency*i/rate))
                                              if block < 35 else 0
                                              for i in range(block*rate//50, (block+1)*rate//50)
                                              for _ in range(channels)))
                    stream.write(signal.tobytes())
report = {'output': output['name'], 'sample_rate': rate,
          'loopback_peak': max(samples, default=0), 'callbacks': len(samples),
          'audio_reached_realtek': max(samples, default=0) > 0}
Path(__file__).with_name('realtek-test.json').write_text(json.dumps(report, indent=2), 'utf-8')
print(json.dumps(report, indent=2))
