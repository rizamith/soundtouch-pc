import comtypes
from pycaw.pycaw import AudioUtilities
from pycaw.api.audiopolicy import IAudioSessionManager2, IAudioSessionControl2

for d in AudioUtilities.GetAllDevices():
    if not (d.id.startswith('{0.0.0.') and d.state.value == 1):
        continue
    print(d.FriendlyName, 'volume', round(d.EndpointVolume.GetMasterVolumeLevelScalar()*100),
          'mute', d.EndpointVolume.GetMute())
    manager = d._dev.Activate(IAudioSessionManager2._iid_, comtypes.CLSCTX_ALL, None).QueryInterface(IAudioSessionManager2)
    sessions = manager.GetSessionEnumerator()
    for i in range(sessions.GetCount()):
        s = sessions.GetSession(i).QueryInterface(IAudioSessionControl2)
        print('  session pid', s.GetProcessId(), 'state', s.GetState())
