import asyncio
import json
import logging
import ssl

import websockets

from discord.ext.commands import AutoShardedBot

from bot.constants import DEBUG_MODE, Keys, URLs


log = logging.getLogger(__name__)


class WS:
    """
    Site WS connection and commands
    """

    ws = None
    reconnect = True  # type: bool

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot
        self.reconnect = True

    async def on_ready(self):
        asyncio.ensure_future(self.ws_connect())

    async def ws_connect(self):
        try:
            url = f"{URLs.site_ws_bot}/{Keys.site_api}"
            if DEBUG_MODE:
                log.warning("Connecting insecurely because we're in debug mode")
                self.ws = await websockets.connect(url)
            else:
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                self.ws = await websockets.connect(url, ssl=ssl_context)
        except Exception:
            self.reconnect = False
            log.exception(f"Failed to connect WS")

        try:
            await self.ws_send({"action": "login", "key": Keys.site_api})
        except Exception:
            log.exception("Failed to send authentication message")
            await self.ws_close()
            return

        while True:
            try:
                # Get data, but don't wait forever for it
                data = await self.ws.recv()
                await self.ws_recv(data)
            except websockets.ConnectionClosed as e:
                log.warning(f"WS is closed: {e}")
                break
            except Exception:
                break

        if self.reconnect:
            log.info("Reconnecting WS...")
            asyncio.ensure_future(self.ws_connect())

    async def ws_send(self, data):
        await self.ws.send(json.dumps(data))

    async def ws_recv(self, data):
        data = json.loads(data)
        action = data.pop("action")

        if action == "login":
            if not data["result"]:
                log.error("Failed to authenticate; incorrect key")
                await self.ws_close()
            else:
                log.info("WS authenticated successfully")

        elif action == "event":
            event = data["event"]
            event_id = event.pop("id")

            log.debug(f"Got event {event_id}: {event}")
        else:
            log.warning(f"Unknown action: {action} | {data}")

    async def ws_close(self):
        log.debug("Closing WS")
        self.reconnect = False

        if self.ws:
            await self.ws.close()

    def __unload(self):
        asyncio.ensure_future(self.ws_close)


def setup(bot):
    bot.add_cog(WS(bot))
    log.info("Cog loaded: WS")
