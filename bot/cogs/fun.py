import logging

from discord import Message
from discord.ext.commands import Bot

from bot.constants import Channels

RESPONSES = {
    "_pokes {us}_": "_Pokes {them}_",
    "_eats {us}_": "_Tastes slimy and snake-like_",
    "_pets {us}_": "_Purrs_"
}

log = logging.getLogger(__name__)


class Fun:
    """
    Fun, entirely useless stuff
    """

    def __init__(self, bot: Bot):
        self.bot = bot

        self.bot.loop.create_task(self.async_init())

    async def async_init(self):
        """
        An alternative "init" that is run at the end of __init__, but this
        one is asynchronous!
        """

        await self.bot.wait_until_ready()
        keys = list(RESPONSES.keys())

        for key in keys:
            changed_key = key.replace("{us}", self.bot.user.mention)

            if key != changed_key:
                RESPONSES[changed_key] = RESPONSES[key]
                del RESPONSES[key]

    async def on_message(self, message: Message):
        if message.channel.id != Channels.bot:
            return

        content = message.content

        if content and content[0] == "*" and content[-1] == "*":
            content = f"_{content[1:-1]}_"

        response = RESPONSES.get(content)

        if response:
            log.debug(
                f"{message.author} said '{message.clean_content}'. Responding with '{response}'.")
            await message.channel.send(response.format(them=message.author.mention))


def setup(bot):
    bot.add_cog(Fun(bot))
    log.info("Cog loaded: Fun")
