# SPDX-License-Identifier: GPL-3.0-or-later
"""aiohttp server: static UI plus a WebSocket that streams MIDI events."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import WSCloseCode, WSMsgType, web

from .monitor import Monitor

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"


def _raise_exit() -> None:
    raise web.GracefulExit()  # asyncio re-raises this from a callback; run_app then cleans up


def graceful_quit() -> None:
    """Stop the whole app the way Ctrl+C does, after a moment so replies can be delivered."""
    asyncio.get_running_loop().call_later(0.3, _raise_exit)


async def index(request: web.Request) -> web.StreamResponse:
    return web.FileResponse(STATIC / "index.html")


async def websocket(request: web.Request) -> web.StreamResponse:
    # Refuse cross-site WebSocket hijacking: only pages served by this app may connect.
    origin = request.headers.get("Origin")
    if origin and urlparse(origin).netloc != request.host:
        raise web.HTTPForbidden(text="cross-origin websocket refused")
    mon: Monitor = request.app["monitor"]
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    request.app["clients"].add(ws)
    try:
        await ws.send_json({"type": "history", "events": list(mon.events)})
        await ws.send_json(mon.state())
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    if isinstance(data, dict) and data.get("cmd") == "quit":
                        log.info("quit requested from the UI")
                        await ws.send_json({"type": "quitting"})
                        request.app["quit"]()
                        continue
                    await mon.command(data)
                except (ValueError, KeyError, TypeError) as e:
                    log.warning("bad command %r: %s", msg.data, e)
    finally:
        request.app["clients"].discard(ws)
    return ws


async def _broadcast(app: web.Application, payload: dict) -> None:
    for ws in list(app["clients"]):
        try:
            await ws.send_json(payload)
        except ConnectionResetError:
            app["clients"].discard(ws)


async def _pump(app: web.Application) -> None:
    mon: Monitor = app["monitor"]
    tick = 0
    while True:
        await asyncio.sleep(0.05)
        events = mon.drain()
        if events:
            await _broadcast(app, {"type": "events", "events": events})
        tick += 1
        if tick % 20 == 0 or app["state_dirty"]:  # state at least once a second
            app["state_dirty"] = False
            await _broadcast(app, mon.state())


def make_app(mon: Monitor, on_quit=graceful_quit) -> web.Application:
    app = web.Application()
    app["monitor"] = mon
    app["quit"] = on_quit
    app["clients"] = set()
    app["state_dirty"] = False
    mon.on_state_change = lambda: app.__setitem__("state_dirty", True)

    async def on_startup(app):
        await mon.start()
        app["pump"] = asyncio.create_task(_pump(app))

    async def on_cleanup(app):
        app["pump"].cancel()
        await mon.stop()

    async def on_shutdown(app):  # close open pages so shutdown doesn't wait on them
        for ws in list(app["clients"]):
            await ws.close(code=WSCloseCode.GOING_AWAY, message=b"server shutdown")

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    app.on_cleanup.append(on_cleanup)
    app.router.add_get("/", index)
    app.router.add_get("/ws", websocket)
    return app
