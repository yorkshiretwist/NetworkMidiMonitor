#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Starts Network MIDI Monitor. On first run it makes a private Python environment in the .venv
# folder next to this file and installs the dependencies into it. Needs Python 3.11 or newer.
# Extra arguments are passed on, for example:  ./run.sh --port 9000 --no-browser
# Set PYTHON to use a particular interpreter, for example:  PYTHON=python3.12 ./run.sh
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"

if ! command -v "$PY" >/dev/null 2>&1 || ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo "Python 3.11 or newer is required but '$PY' was not found or is too old." >&2
    echo "Install it with your package manager, or set PYTHON to another interpreter." >&2
    exit 1
fi

if [ ! -x .venv/bin/python ]; then
    echo "Creating a private Python environment in .venv ..."
    "$PY" -m venv .venv || {
        echo "Could not create the environment. On Debian and Ubuntu, install python3-venv first." >&2
        exit 1
    }
fi

if ! .venv/bin/python -c 'import aiohttp, zeroconf' >/dev/null 2>&1; then
    echo "Installing dependencies ..."
    .venv/bin/python -m pip install --quiet -r requirements.txt
fi

exec .venv/bin/python -m networkmidimonitor "$@"
