"""Discovery and catalog changes must not power on speakers or start audio."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import bridge as module
import discovery


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.config = Path(temporary.name) / 'config.json'
        self.config.write_text(json.dumps({'speaker_name': 'Office', 'speaker_id': 'A',
              'speaker_ip': '192.0.2.10', 'enabled': False,
              'speakers': {'Office': {'id': 'A', 'ip': '192.0.2.10', 'model': 'SoundTouch'}}}), 'utf-8')
        patcher = patch.object(module, 'CONFIG', self.config)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.bridge = module.Bridge()
        self.bridge.route = Mock()
        self.bridge.soap = Mock()
        self.bridge.allow_speaker = Mock()

    def test_scan_preserves_selection_and_updates_catalog_without_playback(self):
        found = [{'name': 'Office', 'id': 'A', 'ip': '192.0.2.11', 'model': 'SA-5'},
                 {'name': 'Kitchen', 'id': 'B', 'ip': '192.0.2.12', 'model': 'SoundTouch 10'}]
        self.bridge.local_ip = Mock(return_value='192.0.2.100')
        with patch.object(discovery, 'scan', return_value=found):
            self.bridge.scan_network()
        self.assertEqual(self.bridge.speaker_name, 'Office')
        self.assertEqual(self.bridge.ip, '192.0.2.11')
        self.assertIn('Kitchen', self.bridge.cfg['speakers'])
        self.assertFalse(self.bridge.enabled)
        self.bridge.route.assert_not_called()
        self.bridge.soap.assert_not_called()
        self.bridge.allow_speaker.assert_not_called()
        self.assertIn('Kitchen', json.loads(self.config.read_text())['speakers'])

    def test_duplicate_names_do_not_overwrite_another_speaker(self):
        self.bridge.merge_speakers([{'name': 'Office', 'id': 'B', 'ip': '192.0.2.12', 'model': 'Other'}])
        self.assertEqual(self.bridge.cfg['speakers']['Office']['id'], 'A')
        self.assertEqual(self.bridge.cfg['speakers']['Office (B)']['id'], 'B')

    def test_any_discovered_room_can_be_selected_without_starting_audio(self):
        self.bridge.merge_speakers([{'name': 'Kitchen', 'id': 'B', 'ip': '192.0.2.12', 'model': 'Other'}])
        self.bridge.select_speaker('Kitchen', play=False)
        self.assertEqual(self.bridge.speaker_name, 'Kitchen')
        self.assertEqual(self.bridge.cfg['speaker_id'], 'B')
        self.assertFalse(self.bridge.enabled)
        self.assertFalse(self.bridge.reconnect.is_set())
        self.bridge.route.assert_not_called()
        self.bridge.allow_speaker.assert_not_called()

    def test_probe_ignores_other_devices(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'<root><device>TV</device></root>'
        with patch.object(discovery.urllib.request, 'urlopen', return_value=response):
            self.assertIsNone(discovery.probe('192.0.2.20'))

    def test_shutdown_another_room_does_not_select_or_route_audio(self):
        self.bridge.merge_speakers([{'name': 'Kitchen', 'id': 'B', 'ip': '192.0.2.12', 'model': 'Other'}])
        self.bridge.enabled = True
        with patch.object(module, 'request', return_value='<nowPlaying deviceID="B" source="SPOTIFY" />') as request:
            self.bridge.shutdown_room('Kitchen')
        self.assertEqual(self.bridge.speaker_name, 'Office')
        self.assertTrue(self.bridge.enabled)
        self.bridge.route.assert_not_called()
        self.bridge.soap.assert_not_called()
        self.assertEqual(request.call_count, 3)
        self.assertTrue(all(call.args[0].startswith('http://192.0.2.12:8090/') for call in request.call_args_list))
        self.assertIn('POWER', request.call_args_list[1].args[1])

    def test_shutdown_standby_room_never_sends_toggle(self):
        self.bridge.merge_speakers([{'name': 'Kitchen', 'id': 'B', 'ip': '192.0.2.12', 'model': 'Other'}])
        with patch.object(module, 'request', return_value='<nowPlaying deviceID="B" source="STANDBY" />') as request:
            self.bridge.shutdown_room('Kitchen')
        request.assert_called_once()
        self.bridge.route.assert_not_called()

    def test_shutdown_rejects_wrong_device_at_saved_address(self):
        self.bridge.merge_speakers([{'name': 'Kitchen', 'id': 'B', 'ip': '192.0.2.12', 'model': 'Other'}])
        with patch.object(module, 'request', return_value='<nowPlaying deviceID="C" source="SPOTIFY" />') as request:
            with self.assertRaises(RuntimeError):
                self.bridge.shutdown_room('Kitchen')
        request.assert_called_once()

    def test_room_status_polling_is_read_only(self):
        self.bridge.merge_speakers([{'name': 'Kitchen', 'id': 'B', 'ip': '192.0.2.12', 'model': 'Other'}])
        def response(url):
            device = 'A' if '192.0.2.10:' in url else 'B'
            return f'<nowPlaying deviceID="{device}" source="STANDBY" />'
        self.bridge.stop.wait = Mock(side_effect=lambda delay: self.bridge.stop.set())
        with patch.object(module, 'request', side_effect=response) as request:
            self.bridge.poll_rooms()
        self.assertEqual(len(self.bridge.room_states), 2)
        self.assertTrue(all(state['state'] == 'Standby' for state in self.bridge.room_states.values()))
        self.assertEqual(request.call_count, 2)
        self.bridge.route.assert_not_called()


if __name__ == '__main__':
    unittest.main()
