# Third-party notices

Network MIDI Monitor is licensed under the [GNU General Public License v3.0 or later](LICENSE). It
uses the third-party software below, each under its own licence. This list is kept by hand; if you
spot a mistake or an omission, please
[open an issue](https://github.com/yorkshiretwist/NetworkMidiMonitor/issues).

## Not affiliated

Network MIDI Monitor is an independent, non-commercial hobby project. It is **not affiliated with,
endorsed by or sponsored by** any company or product named in it. Names are used only to say which
software it was tested with or is compatible with, and belong to their owners:

- **rtpMIDI** is the work of Tobias Erichsen. **QmidiNet** is by Rui Nuno Capela. **rtpmidid** is by
  David Moreno. **ipMIDI** is by nerds.de. **multimidicast** is by its authors.
- **Apple**, **macOS**, **iOS**, **Bonjour** and **Network MIDI** belong to Apple Inc. The RTP-MIDI
  specification is published as RFC 6295 and Apple's session protocol is publicly documented.
- **MIDI** is a standard of the MIDI Manufacturers Association and the Association of Musical
  Electronics Industry.
- **Windows** belongs to Microsoft Corporation, **Linux** to Linus Torvalds, **GitHub** to GitHub, Inc.,
  **JACK**, **PipeWire** and **ALSA** to their respective projects.

## Runtime dependencies

Installed from PyPI by `pip` (they are not copied into this repository). Each also has its own
dependencies, which are listed with their licences on PyPI.

| Component | Licence | Source |
| --- | --- | --- |
| aiohttp | Apache-2.0 and MIT | <https://github.com/aio-libs/aiohttp> |
| zeroconf (python-zeroconf) | LGPL-2.1-or-later | <https://github.com/python-zeroconf/python-zeroconf> |
| ifaddr (installed with zeroconf) | MIT | <https://github.com/ifaddr/ifaddr> |

zeroconf is used as an unmodified, separately installed library, which is how the LGPL expects it to be
used. It is only used to announce the monitor over mDNS when the system's own Bonjour service
(`dns-sd`) is not available.

## Development and test dependencies

Not shipped in the release zip.

| Component | Licence | Source |
| --- | --- | --- |
| pytest | MIT | <https://github.com/pytest-dev/pytest> |
| pytest-asyncio | Apache-2.0 | <https://github.com/pytest-dev/pytest-asyncio> |
| setuptools | MIT | <https://github.com/pypa/setuptools> |

## What the release zip contains

The release zip does not include Python or any of the packages above; `run.bat` / `run.sh` install
them from PyPI on first run.
