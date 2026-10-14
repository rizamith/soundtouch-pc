"""Regression checks for speaker-side controls; no real speaker commands."""
import json
from pathlib import Path
import queue
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import bridge as module


class PlaybackControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / 'config.json'
        self.config.write_text(json.dumps({'speaker_ip': '192.0.2.1', 'speaker_name': 'Test',
                                         'speaker_id': 'TEST', 'enabled': True}), 'utf-8')
        self.patcher = patch.object(module, 'CONFIG', self.config)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.bridge = module.Bridge()
        self.bridge.output_active = True
        self.bridge.reconnect.clear()
        self.bridge.connect = Mock()
        self.bridge.soap = Mock()
        self.bridge.allow_speaker = Mock()

    def poll(self, source, state=None):
        status = f'<playStatus>{state}</playStatus>' if state else ''
        with patch.object(module, 'request', return_value=f'<nowPlaying source="{source}">{status}</nowPlaying>'):
            self.bridge.monitor_once()

    def test_standby_stays_off_with_or_without_an_open_stream(self):
        for open_stream in (False, True):
            with self.subTest(open_stream=open_stream):
                self.bridge.enabled = True
                listener = queue.Queue()
                if open_stream:
                    self.bridge.clients.add(listener)
                self.poll('STANDBY')
                for _ in range(3):
                    self.poll('STANDBY')
                self.bridge.connect.assert_not_called()
                self.bridge.soap.assert_not_called()
                self.assertFalse(self.bridge.enabled)
                self.assertFalse(self.bridge.clients)
                self.assertFalse(json.loads(self.config.read_text())['enabled'])
                self.assertFalse(module.Bridge().enabled)
                if open_stream:
                    self.assertIsNone(listener.get_nowait())

    def test_speaker_pause_and_stop_are_respected(self):
        for state in ('PAUSE_STATE', 'STOP_STATE'):
            with self.subTest(state=state):
                self.bridge.enabled = True
                self.poll('UPNP', state)
                self.assertFalse(self.bridge.enabled)
                self.bridge.connect.assert_not_called()

    def test_transport_disconnect_recovers_when_speaker_still_wants_playback(self):
        for state in ('PLAY_STATE', 'BUFFERING_STATE'):
            with self.subTest(state=state):
                self.bridge.connect.reset_mock()
                self.poll('UPNP', state)
                self.bridge.connect.assert_called_once()
                self.assertTrue(self.bridge.enabled)

    def test_user_can_explicitly_resume_after_switching_off(self):
        self.poll('STANDBY')
        self.bridge.enable()
        self.poll('STANDBY')
        self.bridge.connect.assert_called_once()
        self.assertTrue(self.bridge.enabled)
        self.assertFalse(self.bridge.reconnect.is_set())

    def test_other_sources_are_not_taken_over(self):
        for source in ('SPOTIFY', 'INVALID_SOURCE'):
            with self.subTest(source=source):
                self.poll(source)
                self.bridge.connect.assert_not_called()

    def test_power_buttons_toggle_only_when_needed_and_keep_streaming_paused(self):
        for turn_on in (True, False):
            with self.subTest(turn_on=turn_on):
                state = {'source': 'STANDBY' if turn_on else 'UPNP'}
                keys = []
                def fake_request(url, body=None, headers=None):
                    if body is not None:
                        keys.append(body)
                        if 'state="press"' in body:
                            state['source'] = 'UPNP' if turn_on else 'STANDBY'
                        return '<ok />'
                    return f'<nowPlaying source="{state["source"]}" />'
                with patch.object(module, 'request', side_effect=fake_request):
                    self.bridge.power(turn_on)
                    self.assertEqual(self.bridge.speaker_powered, turn_on)
                    self.assertEqual(len(keys), 2)
                    self.assertIn('state="press"', keys[0])
                    self.assertIn('state="release"', keys[1])
                    self.assertIn('sender="Gabbo"', keys[0])
                    self.bridge.power(turn_on)
                    self.assertEqual(len(keys), 2, 'Repeated action must not toggle the speaker back')
                self.assertFalse(self.bridge.enabled)
                self.assertFalse(self.bridge.reconnect.is_set())
                self.bridge.connect.assert_not_called()

    def test_state_is_refreshed_even_when_the_bridge_is_paused(self):
        self.bridge.enabled = False
        self.poll('STANDBY')
        self.assertTrue(self.bridge.speaker_available)
        self.assertFalse(self.bridge.speaker_powered)
        self.poll('SPOTIFY', 'PLAY_STATE')
        self.assertTrue(self.bridge.speaker_powered)
        self.assertEqual(self.bridge.speaker_state, 'Playing')
        self.bridge.connect.assert_not_called()

    def test_invalid_state_never_triggers_a_power_toggle(self):
        with patch.object(module, 'request', return_value='<errors />') as request:
            with self.assertRaises(RuntimeError):
                self.bridge.power(False)
            self.assertEqual(request.call_count, 1)
            self.assertFalse(self.bridge.enabled)

    def test_this_pc_restores_physical_output_instead_of_another_virtual_cable(self):
        from pycaw.pycaw import AudioUtilities
        prefix = '{0.0.0.00000000}.'
        devices = [SimpleNamespace(id=prefix+'cable', FriendlyName='SoundTouch Wi-Fi (VB-Audio Virtual Cable)', state=SimpleNamespace(value=1)),
                   SimpleNamespace(id=prefix+'cable16', FriendlyName='CABLE In 16ch (VB-Audio Virtual Cable)', state=SimpleNamespace(value=1)),
                   SimpleNamespace(id=prefix+'realtek', FriendlyName='Speakers (Realtek Audio)', state=SimpleNamespace(value=1))]
        self.bridge.cfg['previous_output'] = prefix+'cable16'
        self.bridge.pause = Mock()
        with patch.object(AudioUtilities, 'GetAllDevices', return_value=devices), \
             patch.object(AudioUtilities, 'GetSpeakers', side_effect=[devices[0], devices[2]]), \
             patch.object(AudioUtilities, 'SetDefaultDevice') as select:
            self.bridge.route(False)
        self.assertEqual(select.call_args.args[0], prefix+'realtek')
        self.assertEqual(self.bridge.cfg['previous_output'], prefix+'realtek')
        self.bridge.pause.assert_called_once()

    def test_playing_on_speaker_does_not_save_a_virtual_cable_as_the_local_output(self):
        from pycaw.pycaw import AudioUtilities
        prefix = '{0.0.0.00000000}.'
        devices = [SimpleNamespace(id=prefix+'cable', FriendlyName='SoundTouch Wi-Fi (VB-Audio Virtual Cable)', state=SimpleNamespace(value=1)),
                   SimpleNamespace(id=prefix+'cable16', FriendlyName='CABLE In 16ch (VB-Audio Virtual Cable)', state=SimpleNamespace(value=1))]
        self.bridge.cfg['previous_output'] = 'realtek'
        self.bridge.enable = Mock()
        with patch.object(AudioUtilities, 'GetAllDevices', return_value=devices), \
             patch.object(AudioUtilities, 'GetSpeakers', side_effect=[devices[1], devices[0]]), \
             patch.object(AudioUtilities, 'SetDefaultDevice'):
            self.bridge.route(True)
        self.assertEqual(self.bridge.cfg['previous_output'], 'realtek')


if __name__ == '__main__':
    unittest.main()
