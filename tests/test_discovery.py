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


if __name__ == '__main__':
    unittest.main()
