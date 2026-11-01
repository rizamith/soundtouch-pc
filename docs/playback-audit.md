# Unrequested playback audit — 2026-11-01

Scope: application startup, Windows endpoint changes, speaker discovery,
monitoring, reconnect attempts, volume synchronization, and external standby.
This is a playback-control review, not a full security audit.

## Findings and corrections

1. Startup restored the saved `enabled` flag and set a forced reconnect.
   If the virtual device was selected, this could send Play even in standby.
   Startup now always pauses streaming and leaves no playback request queued.
2. The volume worker enabled playback when Windows switched from a physical
   output to the virtual output. Device re-detection can produce that transition
   without a deliberate user selection. Endpoint changes now only update state.
3. Failed forced requests remained queued; transport recovery also sent Play
   automatically. Playback now makes one attempt directly from an explicit
   panel action. Failures release the session, and polling never sends Play.
4. Volume updates relied on a live HTTP listener and the previous enabled flag.
   A speaker can enter standby before its HTTP connection closes. The volume
   worker now checks the current source/playback state before synchronizing.
5. Changing to another source did not revoke playback permission. External
   standby, pause, stop, source changes, and failed state reads now release it.

Discovery uses SSDP and read-only `/info` requests; it contains no power or
playback commands. Startup shortcuts only launch the application.

## Verification and limits

Offline regression coverage includes saved enabled state at startup, Windows
device re-detection, failed connection followed by network recovery, polling
without automatic Play, external standby with an open stream, and volume
changes while the speaker is in standby. Existing discovery and routing tests
remain in place. Tests mock speakers and never wake real devices.

Speaker state queries and subsequent volume commands are separate network
requests: firmware provides no atomic conditional volume update. A very small
race with an external control remains possible. Other controllers, Spotify,
and Bose firmware are outside this application's control. Logs now identify
explicit playback requests to help distinguish future reports.

The app starts with Windows, but playback requires selecting a room in its
panel. Selecting only the Windows virtual output no longer starts playback.
