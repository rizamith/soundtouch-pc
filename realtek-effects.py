"""Inspect Realtek endpoint and optionally bypass its audio effects, reversibly."""
import argparse
import json
from pathlib import Path
import comtypes
from ctypes import POINTER, c_wchar_p, c_int
from pycaw.pycaw import AudioUtilities
from pycaw.constants import CLSID_CPolicyConfigClient
from pycaw.api.mmdeviceapi.depend.structures import PROPERTYKEY, PROPVARIANT

class Policy(comtypes.IUnknown):
    _iid_ = comtypes.GUID('{f8679f50-850a-41cf-9c72-430f290290c8}')
    _methods_ = [comtypes.COMMETHOD([], comtypes.HRESULT, f'Unused{i}') for i in range(8)] + [
        comtypes.COMMETHOD([], comtypes.HRESULT, 'GetPropertyValue',
                          (['in'], c_wchar_p, 'device'), (['in'], c_int, 'fx'),
                          (['in'], POINTER(PROPERTYKEY), 'key'), (['out'], POINTER(PROPVARIANT), 'value')),
        comtypes.COMMETHOD([], comtypes.HRESULT, 'SetPropertyValue',
                          (['in'], c_wchar_p, 'device'), (['in'], c_int, 'fx'),
                          (['in'], POINTER(PROPERTYKEY), 'key'), (['in'], POINTER(PROPVARIANT), 'value'))]

args = argparse.ArgumentParser()
args.add_argument('--disable', action='store_true')
args.add_argument('--restore', action='store_true')
options = args.parse_args()
device = next(d for d in AudioUtilities.GetAllDevices() if d.id.startswith('{0.0.0.')
              and d.state.value == 1 and 'Realtek' in d.FriendlyName)
endpoint = device.EndpointVolume
print(json.dumps({'device': device.FriendlyName, 'volume': endpoint.GetMasterVolumeLevelScalar(),
                  'channels': [endpoint.GetChannelVolumeLevelScalar(i) for i in range(endpoint.GetChannelCount())],
                  'mute': endpoint.GetMute(), 'hardware_controls': endpoint.QueryHardwareSupport()}))
policy = comtypes.CoCreateInstance(CLSID_CPolicyConfigClient, Policy, comtypes.CLSCTX_ALL)
key = PROPERTYKEY()
key.fmtid = comtypes.GUID('{1da5d803-d492-4edd-8c23-e0c0ffee7f0e}')
key.pid = 5
before = policy.GetPropertyValue(device.id, 0, key)
print('Effects property:', before.vt, before.GetValue())
backup = Path(__file__).with_name('realtek-effects-backup.json')
if options.disable or options.restore:
    value = PROPVARIANT()
    if options.disable:
        if not backup.exists():
            backup.write_text(json.dumps({'vt': before.vt, 'value': before.GetValue()}), 'utf-8')
        value.vt = 19
        value.union.lVal = 1
    else:
        original = json.loads(backup.read_text('utf-8'))
        value.vt = original['vt']
        if value.vt == 19:
            value.union.lVal = int(original['value'])
    policy.SetPropertyValue(device.id, 0, key, value)
    print('Effects updated:', value.vt, value.GetValue())
