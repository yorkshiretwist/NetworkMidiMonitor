# SPDX-License-Identifier: GPL-3.0-or-later
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _names(specs):
    return {re.split(r"[<>=!~ ]", s, maxsplit=1)[0].lower() for s in specs}


def test_requirements_txt_matches_pyproject():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = {s.replace(" ", "") for s in pyproject["project"]["dependencies"]}
    lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    listed = {ln.replace(" ", "") for ln in lines if ln.strip() and not ln.startswith("#")}
    assert listed == declared


def test_version_is_plain_semver():
    from networkmidimonitor import __version__
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_release_notes_have_a_section_for_the_current_version():
    from networkmidimonitor import __version__
    notes = (ROOT / "release.md").read_text(encoding="utf-8")
    assert re.search(rf"^## {re.escape(__version__)}\b", notes, re.M)


def test_every_python_file_has_an_spdx_header():
    files = [*(ROOT / "networkmidimonitor").glob("*.py"), *(ROOT / "tests").glob("*.py"), *(ROOT / "scripts").glob("*.py")]
    missing = [f.name for f in files if "SPDX-License-Identifier: GPL-3.0-or-later" not in f.read_text(encoding="utf-8")[:200]]
    assert not missing
