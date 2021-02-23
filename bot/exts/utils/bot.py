import logging
from typing import Optional

from discord import Embed, TextChannel
from discord.ext.commands import Cog, Context, command, group, has_any_role

from bot.bot import Bot
from bot.constants import Guild, MODERATION_ROLES, URLs

log = logging.getLogger(__name__)


class BotCog(Cog, name="Bot"):
    """Bot information commands."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @group(invoke_without_command=True, name="bot", hidden=True)
    async def botinfo_group(self, ctx: Context) -> None:
        """Bot informational commands."""
        await ctx.send_help(ctx.command)

    @botinfo_group.command(name='about', aliases=('info',), hidden=True)
    async def about_command(self, ctx: Context) -> None:
        """Get information about the bot."""
        embed = Embed(
            description="A utility bot designed just for the Python server! Try `!help` for more info.",
            url="https://github.com/python-discord/bot"
        )

        embed.add_field(name="Total Users", value=str(len(self.bot.get_guild(Guild.id).members)))
        embed.set_author(
            name="Python Bot",
            url="https://github.com/python-discord/bot",
            icon_url=URLs.bot_avatar
        )

        await ctx.send(embed=embed)

    @command(name='echo', aliases=('print',))
    @has_any_role(*MODERATION_ROLES)
    async def echo_command(self, ctx: Context, channel: Optional[TextChannel], *, text: str) -> None:
        """Repeat the given message in either a specified channel or the current channel."""
        if channel is None:
            await ctx.send(text)
        else:
            await channel.send(text)

    @command(name='embed')
    @has_any_role(*MODERATION_ROLES)
    async def embed_command(self, ctx: Context, channel: Optional[TextChannel], *, text: str) -> None:
        """Send the input within an embed to either a specified channel or the current channel."""
        embed = Embed(description=text)

        if channel is None:
            await ctx.send(embed=embed)
        else:
            await channel.send(embed=embed)


def setup(bot: Bot) -> None:
    """Load the Bot cog."""
    bot.add_cog(BotCog(bot))
