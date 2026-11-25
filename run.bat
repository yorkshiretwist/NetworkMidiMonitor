@echo off
rem SPDX-License-Identifier: GPL-3.0-or-later
rem Starts Network MIDI Monitor. On first run it makes a private Python environment in the .venv
rem folder next to this file and installs the dependencies into it. Needs Python 3.11 or newer.
rem Extra arguments are passed on, for example:  .\run.bat --port 9000 --no-browser
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto :nopython
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto :nopython

if exist ".venv\Scripts\python.exe" goto :havevenv
echo Creating a private Python environment in .venv ...
python -m venv .venv
if errorlevel 1 goto :fail

:havevenv
".venv\Scripts\python.exe" -c "import aiohttp, zeroconf" >nul 2>nul
if not errorlevel 1 goto :run
echo Installing dependencies ...
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
if errorlevel 1 goto :fail

:run
".venv\Scripts\python.exe" -m networkmidimonitor %*
exit /b %errorlevel%

:nopython
echo Python 3.11 or newer is required but was not found.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
pause
exit /b 1

:fail
echo Setup failed. See the messages above.
pause
exit /b 1
