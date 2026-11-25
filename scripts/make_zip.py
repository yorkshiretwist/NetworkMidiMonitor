# SPDX-License-Identifier: GPL-3.0-or-later
"""Build dist/NetworkMidiMonitor-<version>.zip: the app, its start scripts and the docs.

    python scripts/make_zip.py          build the zip
    python scripts/make_zip.py --list   print what is in the newest zip (and check it)

The zip does not contain Python or the dependencies: run.bat / run.sh install them from PyPI on
first run. It is built the same way every time (sorted files, fixed timestamps), so the same source
gives the same zip.
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
FIXED_TIME = (2020, 1, 1, 0, 0, 0)  # zip's earliest sensible date, for reproducible output

# Files at the top level of the zip, then folders (copied whole, minus caches).
TOP_FILES = ["README.md", "LICENSE", "THIRD-PARTY-NOTICES.md", "release.md",
             "requirements.txt", "pyproject.toml", "run.bat", "run.sh"]
FOLDERS = ["networkmidimonitor", "docs"]
EXECUTABLE = {"run.sh"}
REQUIRED = {"run.bat", "run.sh", "requirements.txt", "LICENSE", "README.md",
            "networkmidimonitor/__main__.py", "networkmidimonitor/static/index.html"}


def version() -> str:
    text = (ROOT / "networkmidimonitor" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'^__version__ = "(\d+\.\d+\.\d+)"$', text, re.M)
    if not m:
        sys.exit("could not read __version__ from networkmidimonitor/__init__.py")
    return m.group(1)


def files() -> list[Path]:
    found = [ROOT / name for name in TOP_FILES]
    for folder in FOLDERS:
        found += [p for p in (ROOT / folder).rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".pyo"}]
    missing = [p.name for p in found if not p.exists()]
    if missing:
        sys.exit(f"missing files: {', '.join(missing)}")
    return sorted(found, key=lambda p: p.relative_to(ROOT).as_posix())


def build() -> Path:
    v = version()
    DIST.mkdir(exist_ok=True)
    out = DIST / f"NetworkMidiMonitor-{v}.zip"
    top = f"NetworkMidiMonitor-{v}"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in files():
            rel = path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(f"{top}/{rel}", FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if rel in EXECUTABLE else 0o644
            info.external_attr = (mode | 0o100000) << 16  # regular file with unix permissions
            data = path.read_bytes()
            if rel.endswith(".sh"):
                data = data.replace(b"\r\n", b"\n")  # shell scripts must have unix line endings
            elif rel.endswith(".bat"):
                data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")  # cmd needs CRLF or labels break
            z.writestr(info, data)
    print(f"built {out} ({out.stat().st_size / 1024:.0f} KiB)")
    return out


def list_zip() -> None:
    zips = sorted(DIST.glob("NetworkMidiMonitor-*.zip"))
    if not zips:
        sys.exit("no zip in dist/: run this script without --list first")
    path = zips[-1]
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        top = names[0].split("/")[0]
        for info in z.infolist():
            print(f"{info.file_size:>9}  {info.filename}")
        have = {n[len(top) + 1:] for n in names}
        missing = REQUIRED - have
        if missing:
            sys.exit(f"{path.name} is missing: {', '.join(sorted(missing))}")
        if z.testzip():
            sys.exit(f"{path.name} is corrupt")
    print(f"{path.name}: {len(names)} files, all required files present")


if __name__ == "__main__":
    list_zip() if "--list" in sys.argv[1:] else build()
