# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Instead, use GitHub's private
reporting: on the repository's **Security** tab choose **Report a vulnerability**. If that is not
available, open an issue titled "Security concern" **without any details** and I will arrange a
private way for you to share them.

Include what you found, how to reproduce it and the version you tested. This is a hobby project run
by one person, so I cannot promise a response time, but I will try to acknowledge a report within
a week and to fix real problems quickly.

## What is in scope

- **The network parsers** (`networkmidimonitor/rtpmidi.py`, `multicast.py`, `midi.py`): for example a
  crafted RTP-MIDI, session or multicast packet that crashes the monitor, makes it use unbounded
  memory or CPU, or does anything other than show MIDI messages.
- **The web UI and its WebSocket** (`server.py`, `static/index.html`): for example a way for a web
  page on another site, or text carried in a MIDI or session packet (such as a peer name), to run
  script in the UI or send commands to the monitor.
- **The GitHub workflows**: anything that could leak secrets or publish a tampered release.

## Things to know

- **The web UI has no login.** By default it listens only on `127.0.0.1`. The UI can invite RTP-MIDI
  peers and shut the monitor down, so only use `--host` to expose it on a network you trust. Every
  WebSocket connection is checked against the page's own origin, which stops other websites from
  driving a monitor that is running on your computer.
- The monitor only receives and displays MIDI; it never sends MIDI onto the network. It does send
  RTP-MIDI session packets (invitations, clock sync, goodbyes) and announces itself over mDNS.

## Not in scope

- Problems in third-party software (aiohttp, zeroconf, rtpMIDI, QmidiNet and so on) that are
  already reported upstream. Tell me if I should update to a fixed version.
- Anything that needs you to expose the web UI to an untrusted network on purpose.

## Supported versions

Only the latest release is supported.
