"""Verify relocated paths without changing speaker playback."""
import json
from paths import ROOT
from bridge import CONFIG, DATA, Bridge

assert CONFIG == ROOT / 'data' / 'config.json'
assert CONFIG.is_file(), 'Run setup.ps1 to configure the application.'
config = json.loads(CONFIG.read_text('utf-8'))
assert config['speaker_name'] in config['speakers']
assert config['speakers'] and all(speaker['id'] for speaker in config['speakers'].values())
for relative in ('app/bridge.py', 'run.ps1', 'setup.ps1', 'scripts/install.ps1',
                 'scripts/install-shortcuts.ps1', 'scripts/name-output.py', 'scripts/update-firewall.ps1'):
    assert (ROOT / relative).is_file(), f'Missing file: {relative}'
bridge = Bridge()
assert bridge.speaker_name == config['speaker_name']
assert bridge.ip == config['speaker_ip']
print('Application, configuration, log directory, and script paths verified.')
print('Project:', ROOT)
print('Configuration:', CONFIG)
print('Logs:', DATA / 'logs')
print('Driver backups:', DATA / 'backups')
