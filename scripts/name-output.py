"""Rename only the installed VB-CABLE playback endpoint through Windows policy."""
import comtypes
from ctypes import POINTER, c_wchar_p, c_int
from pycaw.pycaw import AudioUtilities
from pycaw.constants import CLSID_CPolicyConfigClient
from pycaw.api.mmdeviceapi.depend.structures import PROPERTYKEY, PROPVARIANT

# Windows 10 property calls include bFxStore. The installed pycaw declaration
# omits that argument; use the Windows 10 ABI for these two methods only.
# Reference: github.com/frgnca/AudioDeviceCmdlets/blob/master/SOURCE/IPolicyConfig.cs
class IPolicyRename(comtypes.IUnknown):
    _iid_ = comtypes.GUID('{f8679f50-850a-41cf-9c72-430f290290c8}')
    _methods_ = [comtypes.COMMETHOD([], comtypes.HRESULT, f'Unused{i}') for i in range(8)] + [
        comtypes.COMMETHOD([], comtypes.HRESULT, 'GetPropertyValue',
                          (['in'], c_wchar_p, 'device'), (['in'], c_int, 'fx'),
                          (['in'], POINTER(PROPERTYKEY), 'key'), (['out'], POINTER(PROPVARIANT), 'value')),
        comtypes.COMMETHOD([], comtypes.HRESULT, 'SetPropertyValue',
                          (['in'], c_wchar_p, 'device'), (['in'], c_int, 'fx'),
                          (['in'], POINTER(PROPERTYKEY), 'key'), (['in'], POINTER(PROPVARIANT), 'value'))]

cable = next(d for d in AudioUtilities.GetAllDevices()
             if d.id.startswith('{0.0.0.') and d.state.value == 1
             and 'VB-Audio Virtual Cable' in d.FriendlyName)
policy = comtypes.CoCreateInstance(CLSID_CPolicyConfigClient, IPolicyRename, comtypes.CLSCTX_ALL)
key = PROPERTYKEY()
key.fmtid = comtypes.GUID('{a45c254e-df1c-4efd-8020-67d146a850e0}')
key.pid = 2
value = PROPVARIANT()
value.vt = 31  # VT_LPWSTR; Python owns this string; don't call PropVariantClear.
value.union.pwszVal = 'SoundTouch Wi-Fi'
policy.SetPropertyValue(cable.id, 0, key, value)
print('Renamed:', AudioUtilities.CreateDevice(cable._dev).FriendlyName)
