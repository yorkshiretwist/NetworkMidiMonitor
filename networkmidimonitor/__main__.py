# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import logging
import webbrowser

from aiohttp import web

from . import __version__
from .monitor import Monitor, Settings
from .server import make_app


def main() -> None:
    ap = argparse.ArgumentParser(prog="networkmidimonitor", description="Monitor RTP-MIDI and UDP multicast MIDI.")
    ap.add_argument("--host", default="127.0.0.1", help="address for the web UI (default: localhost only)")
    ap.add_argument("--port", type=int, default=8080, help="web UI port (default 8080)")
    ap.add_argument("--no-browser", action="store_true", help="don't open the browser")
    ap.add_argument("--no-mdns", action="store_true", help="don't advertise the RTP-MIDI session over mDNS")
    ap.add_argument("-v", "--verbose", action="store_true", help="log debug detail")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    app = make_app(Monitor(Settings(), advertise=not args.no_mdns))
    if not args.no_browser:
        async def open_browser(_app):
            webbrowser.open(f"http://{args.host}:{args.port}/")
        app.on_startup.append(open_browser)
    web.run_app(app, host=args.host, port=args.port, print=lambda *_: print(
        f"Network MIDI Monitor: http://{args.host}:{args.port}/  (Ctrl+C to quit)"))


if __name__ == "__main__":
    main()
