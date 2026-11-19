
from discord import Embed, TextChannel, app_commands
from discord.ext.commands import Cog, Context, has_any_role

from bot.bot import Bot
from bot.constants import Guild, MODERATION_ROLES, URLs
from bot.log import get_logger
from bot.utils.hybrid import hybrid_command, hybrid_group

log = get_logger(__name__)


class BotCog(Cog, name="Bot"):
    """Bot information commands."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @hybrid_group(invoke_without_command=True, name="bot", hidden=True)
    async def botinfo_group(self, ctx: Context) -> None:
        """Bot informational commands."""
        await ctx.send_help(ctx.command)

    @botinfo_group.command(name="about", aliases=("info",), hidden=True)
    async def about_command(self, ctx: Context) -> None:
        """Get information about the bot."""
        embed = Embed(
            description=(
                "A utility bot designed just for the Python server! "
                "Try `/help` for more info."
            ),
            url="https://github.com/python-discord/bot"
        )

        embed.add_field(name="Total Users", value=str(len(self.bot.get_guild(Guild.id).members)))
        embed.set_author(
            name="Python Bot",
            url="https://github.com/python-discord/bot",
            icon_url=URLs.bot_avatar
        )

        await ctx.send(embed=embed)

    @hybrid_command(name="echo", aliases=("print",))
    @app_commands.describe(
        channel="The channel to send the message in, defaults to the current channel",
        text="The text to send",
    )
    @has_any_role(*MODERATION_ROLES)
    async def echo_command(self, ctx: Context, channel: TextChannel | None, *, text: str) -> None:
        """Repeat the given message in either a specified channel or the current channel."""
        if channel is None:
            await ctx.send(text)
        elif not channel.permissions_for(ctx.author).send_messages:
            await ctx.send("You don't have permission to speak in that channel.", ephemeral=True)
        else:
            await channel.send(text)
            if ctx.interaction is not None:
                await ctx.send(f"Sent your message in {channel.mention}.", ephemeral=True)

    @hybrid_command(name="embed")
    @app_commands.describe(
        channel="The channel to send the embed in, defaults to the current channel",
        text="The text of the embed",
    )
    @has_any_role(*MODERATION_ROLES)
    async def embed_command(self, ctx: Context, channel: TextChannel | None, *, text: str) -> None:
        """Send the input within an embed to either a specified channel or the current channel."""
        embed = Embed(description=text)

        if channel is None:
            await ctx.send(embed=embed)
        else:
            await channel.send(embed=embed)
            if ctx.interaction is not None:
                await ctx.send(f"Sent your embed in {channel.mention}.", ephemeral=True)


async def setup(bot: Bot) -> None:
    """Load the Bot cog."""
    await bot.add_cog(BotCog(bot))
