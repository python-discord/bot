import json
from pathlib import Path

from discord.ext import commands

from bot import constants
from bot.bot import Bot

ASKING_GUIDE_URL = "https://pythondiscord.com/pages/asking-good-questions/"

AVAILABLE_MSG = f"""
This help channel is now **available**, which means that you can claim it by simply typing your \
question into it. Once claimed, the channel will move into the **Help: In Use** category, and will \
be yours until it has been inactive for {constants.HelpChannels.idle_minutes}. When that happens, \
it will be set to **dormant** and moved into the **Help: Dormant** category.

Try to write the best question you can by providing a detailed description and telling us what \
you've tried already. For more information on asking a good question, \
[check out our guide on asking good questions]({ASKING_GUIDE_URL}).
"""

DORMANT_MSG = f"""
This help channel has been marked as **dormant**, and has been moved into the **Help: Dormant** \
category at the bottom of the channel list. It is no longer possible to send messages in this \
channel until it becomes available again.

If your question wasn't answered yet, you can claim a new help channel from the \
**Help: Available** category by simply asking your question again. Consider rephrasing the \
question to maximize your chance of getting a good answer. If you're not sure how, have a look \
through [our guide for asking a good question]({ASKING_GUIDE_URL}).
"""

with Path("bot/resources/elements.json").open(encoding="utf-8") as elements_file:
    ELEMENTS = json.load(elements_file)


class HelpChannels(commands.Cog):
    """Manage the help channel system of the guild."""


def setup(bot: Bot) -> None:
    """Load the HelpChannels cog."""
    bot.add_cog(HelpChannels(bot))
