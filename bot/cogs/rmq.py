import json
import logging

import aio_pika
from discord.ext.commands import AutoShardedBot

from bot.constants import Channels, RabbitMQ

log = logging.getLogger(__name__)


class RMQ:
    """
    RabbitMQ event handling
    """

    rmq = None  # type: aio_pika.Connection
    channel = None  # type: aio_pika.Channel
    queue = None  # type: aio_pika.Queue

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    async def on_ready(self):
        self.rmq = await aio_pika.connect_robust(
            host=RabbitMQ.host, port=RabbitMQ.port, login=RabbitMQ.username, password=RabbitMQ.password
        )

        log.info("Connected to RabbitMQ")

        self.channel = await self.rmq.channel()
        self.queue = await self.channel.declare_queue("bot_events", durable=True)

        log.debug("Channel opened, queue declared")

        async for message in self.queue:
            with message.process():
                await self.handle_message(message, message.body.decode())

    async def handle_message(self, message, data):
        log.debug(f"Message: {message}")
        log.debug(f"Data: {data}")

        try:
            data = json.loads(data)
            await self.send_test(f"JSON: {data}")
        except Exception:
            await self.send_test(f"Non-JSON: {data}")

    async def send_test(self, data):
        await self.bot.get_channel(Channels.devtest).send(data)


def setup(bot):
    bot.add_cog(RMQ(bot))
    log.info("Cog loaded: RMQ")
