import arrow
from aiohttp import client_exceptions
from discord import Embed
from discord.ext import commands

from bot.bot import Bot
from bot.constants import Channels, STAFF_PARTNERS_COMMUNITY_ROLES, URLs
from bot.decorators import in_whitelist

DESCRIPTIONS = (
    "Command processing time",
    "Python Discord website status",
    "Discord API latency"
)
ROUND_LATENCY = 3


class Latency(commands.Cog):
    """Getting the latency between the bot and websites."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @commands.command()
    @in_whitelist(channels=(Channels.bot_commands,), roles=STAFF_PARTNERS_COMMUNITY_ROLES)
    async def ping(self, ctx: commands.Context) -> None:
        """
        Gets different measures of latency within the bot.

        Returns bot, Python Discord Site, Discord Protocol latency.
        """
        # datetime.datetime objects do not have the "milliseconds" attribute.
        # It must be converted to seconds before converting to milliseconds.
        bot_ping = (arrow.utcnow() - ctx.message.created_at).total_seconds() * 1000
        if bot_ping <= 0:
            bot_ping = "Your clock is out of sync, could not calculate ping."
        else:
            bot_ping = f"{bot_ping:.{ROUND_LATENCY}f} ms"

        try:
            async with self.bot.http_session.get(f"{URLs.site_api}/healthcheck") as request:
                request.raise_for_status()
                site_status = "Healthy"

        except client_exceptions.ClientResponseError as e:
            """The site returned an unexpected response."""
            site_status = f"The site returned an error in the response: ({e.status}) {e}"
        except client_exceptions.ClientConnectionError:
            """Something went wrong with the connection."""
            site_status = "Could not establish connection with the site."

        # Discord Protocol latency return value is in seconds, must be multiplied by 1000 to get milliseconds.
        discord_ping = f"{self.bot.latency * 1000:.{ROUND_LATENCY}f} ms"

        embed = Embed(title="Pong!")

        for desc, latency in zip(DESCRIPTIONS, [bot_ping, site_status, discord_ping], strict=True):
            embed.add_field(name=desc, value=latency, inline=False)

        await ctx.send(embed=embed)


async def setup(bot: Bot) -> None:
    """Load the Latency cog."""
    await bot.add_cog(Latency(bot))
