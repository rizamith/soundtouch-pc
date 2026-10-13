# SoundTouch PC

Stream Windows audio to Bose SoundTouch speakers over your local Wi-Fi network.

SoundTouch PC captures Windows playback audio through WASAPI, encodes stereo
MP3 at 320 kbps, and serves a live HTTP stream to the selected speaker using
its UPnP renderer. Audio streaming and speaker control use local network
interfaces and do not require the Bose cloud service.

The current interface supports **Quartos** (a SoundTouch SA-5), **Sala** (a Bose
Cinemate with SoundTouch), and the PC's local audio output. Other models have
not been verified; this is not currently a universal DLNA speaker picker.
The desktop interface is in Portuguese. Room names and button labels below
match that interface.

## Features

- Play audio from VLC, browsers, and other Windows applications on a Bose speaker.
- Choose Quartos, Sala, or the PC's local output from a desktop panel.
- Control speaker volume and mute with the Windows slider and keyboard keys.
- Reflect changes made on the speaker back in the Windows volume slider.
- Preserve each speaker's volume when switching rooms.
- Remember the selected room and start automatically when you sign in to Windows.
- Release the speaker for Spotify or another source.
- Detect changes to the default Windows output and retry network connections.

## Requirements

- Windows 10 or 11, 64-bit.
- Python 3.14, 64-bit, available as `python` in PowerShell.
- Both configured SoundTouch speakers accessible on the PC's local network.
- [VB-CABLE for Windows](https://vb-audio.com/Cable/), installed separately.
- Administrator privileges for driver installation and firewall configuration.

VB-CABLE is a virtual audio device. The Windows output named **SoundTouch Wi-Fi**
is that virtual device, renamed by this project. The bridge then sends its
audio to the physical Bose speaker. Network discovery alone does not turn a
speaker into a native Windows playback device.

## Installation

1. Clone the repository into a permanent folder:

   ```powershell
   git clone https://github.com/rizamith/soundtouch-pc.git
   cd soundtouch-pc
   ```

2. Adjust the IP addresses in `config.example.json` if necessary. The example
   uses `192.168.1.88` for Quartos and `192.168.1.90` for Sala. The speaker
   names must match those rooms.

3. Create the Python environment and local configuration:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
   ```

   This installs pinned dependencies into `.venv` and queries the speakers to
   generate `config.json` with their actual IDs. An existing configuration
   is preserved. Use `-PythonCommand` to specify another Python executable.

4. Download the Windows VB-CABLE package from its
   [official website](https://vb-audio.com/Cable/) and extract its contents
   into `vendor\vbcable`. Skip this step if VB-CABLE is already installed.
   The third-party installer and driver are not distributed in this repository.

5. Open PowerShell as administrator and run:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\admin-setup.ps1
   ```

   This adds the firewall rule and opens the official VB-CABLE installer when
   needed. Choose **Install Driver** and restart Windows if requested.
   The installer signature is checked before it is launched.

6. Start the panel and create the desktop and Startup shortcuts:

   ```powershell
   .\.venv\Scripts\pythonw.exe .\bridge.py --panel
   powershell -NoProfile -ExecutionPolicy Bypass -File .\install-shortcuts.ps1
   ```

   The **SoundTouch** shortcut starts the application. It also launches
   automatically when you sign in to Windows.

If VB-CABLE was already the default output during setup, first select your
local speakers in Windows, then select Quartos or Sala in the panel. This
lets the bridge remember the local output to restore when you choose the PC.

## Everyday use

Double-click the green system-tray icon to open the panel.

| Panel control | Behavior |
| --- | --- |
| **Quartos** | Stop the previous speaker stream and play PC audio in Quartos. |
| **Sala** | Stop the previous speaker stream and play PC audio in Sala. |
| **Este PC** | Restore the previous local Windows output and pause streaming. |
| Volume slider | Adjust the selected speaker's volume; Windows volume keys work too. |
| **Usar Spotify** | Pause streaming and release the speaker for another source. |
| **Restabelecer ligação** | Reconnect the selected speaker to the PC stream. |

Selecting **SoundTouch Wi-Fi** in the Windows output selector activates the
bridge for the last selected room. The bridge does not force playback back
to the PC if you subsequently select Spotify on the speaker.

Application volume controls, such as VLC's slider, still affect their own
audio. The Windows master slider is synchronized with the selected speaker.
On connection, the bridge adopts the speaker's current volume to avoid a jump
to a stale virtual-device setting.

Closing the panel leaves the bridge running. Choose **Sair** in the tray menu
to quit; the application attempts to restore the local PC output.

## Configuration and backups

`config.json` contains the selected room, speaker addresses and IDs, HTTP
port, and previous local Windows output. It is generated locally and ignored
by Git. Keep a separate copy to restore this PC's exact configuration.

The default stream port is TCP **18788**. The firewall rule restricts inbound
traffic to the two configured speaker IP addresses. The stream endpoint also
checks the requesting IP address and uses a random URL token. Status requests
are accepted only from localhost.

SSDP attempts to rediscover the selected speaker if its IP changes, but the
firewall must still allow its current address. DHCP reservations are recommended.
Run `add-sala-firewall.ps1` as administrator to refresh the existing firewall
address filter from `config.json`.

Python environments, installers, driver backups, logs, generated icons, test
results, and local configuration are excluded from Git.

## Limitations

- Encoding and the SoundTouch buffer introduce latency. Games or calls may
  be unsuitable, and video can require manual audio synchronization in VLC.
  Automatic video synchronization is not implemented.
- The PC, application, and selected speaker must remain available on the same network.
- One speaker is selected at a time; synchronized multi-room playback is not implemented.
- If a speaker belongs to a group led by another speaker, ungroup it in the
  SoundTouch application before using the bridge.
- Compatibility was verified with the SA-5 in Quartos and the Cinemate in Sala.
  Other models and arbitrary DLNA renderers have not been verified.

The bridge captures playback audio, not the microphone, and does not save
the audio stream to disk.

## Diagnostics and verification

Status is available at `http://127.0.0.1:18788/status` while the bridge runs.
The rotating `bridge.log` records connections, capture failures, and volume updates.

| Tool | Purpose |
| --- | --- |
| `python -m py_compile bridge.py` | Check Python syntax without playing audio. |
| `check-speaker-switch.py` | Test streaming and volume synchronization in both rooms. Quit the tray app first to free the HTTP port. This temporarily changes both speakers' sources. |
| `generate-test-tone.py`, then `check-audio.py` | Generate a quiet tone and verify capture and delivery through the running bridge. |
| `inspect-outputs.py` | Inspect playback devices, volume, mute, and audio sessions. |
| `test-realtek.py` | Play tones directly through Realtek, independently of the bridge. |
| `restart-realtek.ps1` | ASUS PB60 repair helper: back up the matching Realtek driver and restart that device. Requires administrator privileges. |
| `realtek-effects.py` | Inspect Realtek effects. Optional `--disable` and `--restore` switches modify or restore effects using a local backup. |

Run Python diagnostics using `.\.venv\Scripts\python.exe`. Audio tests can
produce audible tones. Realtek repair helpers are optional and are not part
of normal bridge operation. In the original setup, restarting Realtek restored
the PC's internal speaker output without reinstalling its driver.

## Uninstalling or moving the application

Choose **Este PC**, then **Sair**. Remove the desktop and Startup shortcuts.
Remove the firewall rule named `SoundTouch Quartos - audio local` using an
administrator PowerShell window. Remove VB-CABLE with its official installer
and restart Windows as instructed by the manufacturer.

To move the project, quit it before moving the folder, recreate `.venv` with
`setup.ps1` if necessary, and rerun `install-shortcuts.ps1` from the new location.
Existing shortcuts and Python launchers can contain absolute paths.

## Support development

If this project is useful to you, you can support its development through PayPal:

[**Contribute via PayPal**](https://paypal.me/RZamith)

Contributions are optional. The link opens the project's PayPal.Me profile,
where you can choose the amount you would like to contribute.

## References

- [VB-CABLE](https://vb-audio.com/Cable/)
- [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch)
- [Bose SoundTouch API documentation](https://assets.bosecreative.com/m/496577402d128874/original/SoundTouch-Web-API.pdf)
