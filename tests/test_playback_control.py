"""Regression checks for speaker-side controls; no real speaker commands."""
import json
from pathlib import Path
import queue
import sys
import tempfile
import unittest
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


if __name__ == '__main__':
    unittest.main()
