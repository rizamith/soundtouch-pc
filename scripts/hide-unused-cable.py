"""Disable unused VB-CABLE endpoints, preserving the SoundTouch loopback output.

Run with --restore to restore endpoint visibility recorded before the first run.
No drivers are removed and no physical microphone defaults are changed.
"""
import argparse
import json
from pathlib import Path

import comtypes
from pycaw.api.policyconfig import IPolicyConfig
from pycaw.constants import CLSID_CPolicyConfigClient
from pycaw.pycaw import AudioUtilities


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    backup = Path(__file__).resolve().parents[1] / 'data' / 'backups' / 'unused-cable-endpoints.json'
    devices = AudioUtilities.GetAllDevices()
    targets = [d for d in devices if
               (d.id.startswith('{0.0.1.') and d.FriendlyName == 'CABLE Output (VB-Audio Virtual Cable)') or
               (d.id.startswith('{0.0.0.') and d.FriendlyName == 'CABLE In 16ch (VB-Audio Virtual Cable)')]
    soundtouch = next(d for d in devices if d.id.startswith('{0.0.0.')
                     and d.FriendlyName == 'SoundTouch Wi-Fi (VB-Audio Virtual Cable)')
    if soundtouch.state.value != 1:
        raise RuntimeError('SoundTouch output must be active before changing unused endpoints.')
    if not args.restore and not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(json.dumps([{'id': d.id, 'name': d.FriendlyName,
                                       'visible': not bool(d.state.value & 2)} for d in targets], indent=2), 'utf-8')
    saved = json.loads(backup.read_text('utf-8'))
    policy = comtypes.CoCreateInstance(CLSID_CPolicyConfigClient, IPolicyConfig, comtypes.CLSCTX_ALL)
    for device in targets:
        original = next((row for row in saved if row['id'] == device.id), None)
        if original is None:
            raise RuntimeError('Endpoint has no backup; inspect it before changing visibility.')
        visible = original['visible'] if args.restore else False
        policy.SetEndpointVisibility(device.id, visible)
        print(('Restored' if visible else 'Disabled') + ': ' + device.FriendlyName)
    refreshed = {d.id: d for d in AudioUtilities.GetAllDevices()}
    if refreshed[soundtouch.id].state.value != 1:
        raise RuntimeError('SoundTouch output is no longer active; inspect audio settings.')
    for device in targets:
        if not args.restore and refreshed[device.id].state.value != 2:
            raise RuntimeError('Windows did not disable ' + device.FriendlyName)
    print('SoundTouch playback output remains active.')


if __name__ == '__main__':
    main()
