"""Generate a quiet, alternating six-second tone for check-audio.py."""
import math
from pathlib import Path
import struct
import wave

with wave.open(str(Path(__file__).with_name('test-tone.wav')), 'wb') as wav:
    wav.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
    wav.writeframes(b''.join(struct.pack('<hh', *[int(1100*math.sin(2*math.pi*440*i/48000))
                                                if i % 48000 < 24000 else 0]*2)
                            for i in range(48000*6)))
