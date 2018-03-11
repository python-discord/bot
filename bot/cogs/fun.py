# coding=utf-8
import logging

from discord import Message
from discord.ext.commands import AutoShardedBot

from bot.constants import BOT_CHANNEL

RESPONSES = {
    "_pokes {us}_": "_Pokes {them}_",
    "_eats {us}_": "_Tastes slimy and snake-like_",
    "_pets {us}_": "_Purrs_"
}

log = logging.getLogger(__name__)


class Fun:
    """
    Fun, mostly-useless stuff
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    async def on_ready(self):
        keys = list(RESPONSES.keys())

        for key in keys:
            changed_key = key.replace("{us}", self.bot.user.mention)

            if key != changed_key:
                RESPONSES[changed_key] = RESPONSES[key]
                del RESPONSES[key]

    async def on_message(self, message: Message):
        if message.channel.id != BOT_CHANNEL:
            return

        content = message.content

        if content and content[0] == "*" and content[-1] == "*":
            content = f"_{content[1:-1]}_"

        response = RESPONSES.get(content)

        if response:
            log.info(f"{message.author} said '{content}'. Responding with '{response}'.")
            await message.channel.send(response.replace("{them}", message.author.mention))


def setup(bot):
    bot.add_cog(Fun(bot))
    log.info("Cog loaded: Fun")
