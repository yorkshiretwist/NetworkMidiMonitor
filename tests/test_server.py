# SPDX-License-Identifier: GPL-3.0-or-later
import asyncio

import aiohttp
from aiohttp.test_utils import TestServer

from networkmidimonitor.monitor import Monitor, Settings
from networkmidimonitor.server import make_app


async def test_quit_command_replies_and_calls_quit(tmp_path):
    settings = Settings(tmp_path / "s.json")
    settings.data.update(mc_ports=[], rtp_port=15050)  # don't touch the real ports
    quits = []
    server = TestServer(make_app(Monitor(settings, advertise=False), on_quit=lambda: quits.append(1)))
    await server.start_server()
    try:
        async with aiohttp.ClientSession() as http:
            async with http.ws_connect(server.make_url("/ws")) as ws:
                await ws.send_json({"cmd": "quit"})
                seen = []
                while "quitting" not in seen:
                    seen.append((await asyncio.wait_for(ws.receive_json(), 3))["type"])
        assert quits == [1]
    finally:
        await server.close()


async def test_websocket_rejects_cross_origin(tmp_path):
    settings = Settings(tmp_path / "s.json")
    settings.data.update(mc_ports=[], rtp_port=15052)
    server = TestServer(make_app(Monitor(settings, advertise=False)))
    await server.start_server()
    try:
        async with aiohttp.ClientSession() as http:
            try:
                await http.ws_connect(server.make_url("/ws"), headers={"Origin": "http://evil.example"})
                assert False, "cross-origin websocket was accepted"
            except aiohttp.WSServerHandshakeError as e:
                assert e.status == 403
    finally:
        await server.close()
