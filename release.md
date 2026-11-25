# Releases

The notes for each release, newest first. A release is published only when you push a version tag
on a commit that is on `main` (see [CONTRIBUTING.md](CONTRIBUTING.md#making-a-release)); editing this
file or anything else on `main` never builds one. The section whose heading is `## <version>`
(for example `## 0.1.0 - 2026-11-25`) becomes the release notes for the tag `v<version>`.

## 0.1.0 - 2026-11-25

First release.

**What it does.** A live, read-only monitor that shows MIDI messages from RTP-MIDI (Apple Network
MIDI: rtpMIDI, rtpmidid, macOS) and from UDP multicast MIDI (QmidiNet, ipMIDI) in one browser window.
It runs on Windows and Linux with Python 3.11 or newer.

- **Log tab:** a live table of messages (time, source, channel, decoded message, raw bytes on hover)
  with search, a message-type filter, channel filtering from the channel meter, pause and clear.
- **Timeline tab:** note bars, controller and pitch-bend ticks over the last 5, 10, 30 or 60 seconds,
  grouped by source and channel.
- **RTP-MIDI:** joins as a session peer. It announces itself over Bonjour/mDNS, accepts invitations
  and can invite a peer by `host:port`. Lost packets are counted.
- **Multicast:** listens on up to four cables (`225.0.0.37`, ports 21928 to 21931) on the network
  interface you pick.
- **Quit** button for a clean shutdown.

**Known limits.** The RTP-MIDI recovery journal is ignored (losses are counted, not repaired). There
is no MIDI output. Tested against rtpMIDI on Windows, rtpmidid and QmidiNet on Linux; not yet run on
Linux or macOS as the host.
