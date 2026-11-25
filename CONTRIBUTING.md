# Contributing to Network MIDI Monitor

Thank you for thinking of helping! This is a small hobby project, so please be patient with replies.
By taking part you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to help

- **Report a bug** or ask a question: [open an issue](https://github.com/yorkshiretwist/NetworkMidiMonitor/issues/new/choose).
  Say what you did, what you expected and what happened, and include your operating system, Python
  version, the monitor version (`python -m networkmidimonitor --version`) and which software is sending
  the MIDI (rtpMIDI, rtpmidid, QmidiNet, ipMIDI, ...).
- **Report that it works** (or doesn't) with a sender or platform that is not listed in the README, such
  as macOS's Network MIDI session, an iPad app, a hardware RTP-MIDI device or a different multicast tool.
  That is very useful, and a note in an issue is enough.
- **Suggest a feature.** Explain the problem you want solved, not just the solution.
- **Improve the documentation**, especially the step-by-step connection guides.
- **Send a pull request.** For anything bigger than a small fix, open an issue first so we can agree
  the approach before you spend time on it.

## Licensing of contributions

Network MIDI Monitor is licensed under the [GNU General Public License v3.0 or later](LICENSE). By
submitting a contribution you confirm that you wrote it (or have the right to share it) and that you
license it under the same terms (GPL-3.0-or-later). There is no separate contributor agreement. If you
add code or files from somewhere else, say where from and under which licence, and add it to
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md); it must be compatible with the GPL. New source files
start with the line `SPDX-License-Identifier: GPL-3.0-or-later` in a comment.

## What is where

| Path | What it is |
| --- | --- |
| `networkmidimonitor/` | The Python package: MIDI parser, RTP-MIDI session peer, multicast listener, web server |
| `networkmidimonitor/static/index.html` | The whole web UI (one file, plain JavaScript, no build step) |
| `tests/` | The test suite (pytest) |
| `docs/developers.md` | How it works: read this before changing the network code |
| `scripts/` | Packaging scripts used by the release workflow |
| `.github/` | CI, the release workflow, issue and pull request templates |

## Setting up

You need Python 3.11 or newer.

```bash
git clone https://github.com/yorkshiretwist/NetworkMidiMonitor.git
cd NetworkMidiMonitor
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux/macOS: source .venv/bin/activate
pip install -e ".[test]"
python -m networkmidimonitor        # run it
pytest                              # run the tests
```

## Tests

Run `pytest` before opening a pull request; [CI](.github/workflows/ci.yml) runs it on Linux and Windows
with Python 3.11 to 3.14. The tests use only the loopback interface and high local ports, so they
do not need other machines, MIDI software or the network.

What the tests cannot cover is real software on a real network. If you change the RTP-MIDI or multicast
code, please also try it against rtpMIDI (Windows/macOS), rtpmidid (Linux) or QmidiNet / ipMIDI, and say
which in the pull request. The README's [connecting guide](README.md#connecting-your-midi-sources)
lists the steps.

## Pull requests

- Keep each pull request to one change, and describe what it does and why.
- Add or update tests, and make sure the tests pass.
- Match the style of the surrounding code and comments.
- Update the README and [docs/developers.md](docs/developers.md) if behaviour changes.
- Do not commit virtual environments, build output or your own settings file.
- The UI is a single static file on purpose: no frameworks or build step. Please keep it that way
  unless we have agreed otherwise in an issue. Anything that came from the network (peer names,
  sources) must be put on the page with `textContent`, never `innerHTML`.

## Making a release

Only the maintainer does this. A release is built and published **only when a version tag is pushed**
on a commit that is on `main`. Pushing to `main` (including docs) never creates a release.

1. Add a section for the new version at the top of [`release.md`](release.md), headed
   `## <major>.<minor>.<patch> - <date>`; its text becomes the release notes.
2. Set the version in `networkmidimonitor/__init__.py` (`__version__`). The release workflow stops if
   it does not match the tag.
3. Merge to `main`, then tag and push:

   ```bash
   git checkout main && git pull
   git tag v0.2.0
   git push origin v0.2.0
   ```

4. The [release workflow](.github/workflows/release.yml) runs the tests, builds the zip and attaches it,
   with checksums, to a new GitHub release. If a tag was a mistake, delete the release and the tag
   (`git push origin --delete v0.2.0`) and tag again.

You can try the packaging without publishing anything: `python scripts/make_zip.py` builds
`dist/NetworkMidiMonitor-<version>.zip` locally.
