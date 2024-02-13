import datetime

import arrow
import discord
from discord.ext import commands, tasks
from pydis_core.utils.channel import get_or_fetch_channel

from bot import constants
from bot.bot import Bot
from bot.constants import Channels, Guild, Roles, STAFF_PARTNERS_COMMUNITY_ROLES
from bot.decorators import in_whitelist
from bot.log import get_logger

log = get_logger(__name__)

PATREON_INFORMATION = (
    "Python Discord is a volunteer run non-profit organization, so we rely on Patreon donations to do what we do. "
    "We use the money we get to offer excellent prizes for all of our events. These include t-shirts, "
    "stickers, and sometimes even Raspberry Pis!\n\n"
    "You can read more about how Patreon donations help us, and consider donating yourself, on our patreon page "
    "[here](https://pydis.com/patreon)!"
)
NO_PATRONS_MESSAGE = "*There are currently no patrons at this tier.*"

# List of tuples containing tier number and Discord role ID.
# Ordered from highest tier to lowest.
PATREON_TIERS: list[tuple[int, int]] = [
    (3, Roles.patreon_tier_3),
    (2, Roles.patreon_tier_2),
    (1, Roles.patreon_tier_1),
]


def get_patreon_tier(member: discord.Member) -> int:
    """
    Get the patreon tier of `member`.

    A patreon tier of 0 indicates the user is not a patron.
    """
    for tier, role_id in PATREON_TIERS:
        if member.get_role(role_id):
            return tier
    return 0


class Patreon(commands.Cog):
    """Cog that shows patreon supporters."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

        self.current_monthly_supporters.start()

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Send a message when someone receives a patreon role."""
        old_patreon_tier = get_patreon_tier(before)
        new_patreon_tier = get_patreon_tier(after)

        if new_patreon_tier <= old_patreon_tier:
            return

        message = (
            f":tada: {after.mention} just became a **tier {new_patreon_tier}** patron!\n"
            "Support us on Patreon: https://pydis.com/patreon"
        )
        channel = await get_or_fetch_channel(self.bot, Channels.meta)
        await channel.send(message)

    async def send_current_supporters(self, channel: discord.abc.Messageable, automatic: bool = False) -> None:
        """Send the current list of patreon supporters, sorted by tier level."""
        guild = self.bot.get_guild(Guild.id)

        embed_list = []
        for tier, role_id in PATREON_TIERS:
            role = guild.get_role(role_id)

            # Filter out any members where this is not their highest tier.
            patrons = [member for member in role.members if get_patreon_tier(member) == tier]
            patron_names = [f"- {patron}" for patron in patrons]

            embed = discord.Embed(
                title=role.name,
                description="\n".join(patron_names) if patron_names else NO_PATRONS_MESSAGE,
                colour=role.colour
            )
            embed_list.append(embed)

        main_embed = discord.Embed(
            title="Patreon Supporters - Monthly Update" if automatic else "Patreon Supporters",
            description=(
                PATREON_INFORMATION +
                "\n\nThank you to the users listed below who are already supporting us!"
            ),
        )

        await channel.send(embeds=(main_embed, *embed_list))

    @commands.group("patreon", aliases=("patron",), invoke_without_command=True)
    async def patreon_info(self, ctx: commands.Context) -> None:
        """Send information about how Python Discord uses Patreon."""
        embed = discord.Embed(
            title="Patreon",
            description=(
                PATREON_INFORMATION +
                "\n\nTo see our current supporters, run " +
                f"`{constants.Bot.prefix}patreon supporters` in <#{Channels.bot_commands}>"
            )
        )
        await ctx.send(embed=embed)

    @patreon_info.command("supporters", aliases=("patrons",))
    @in_whitelist(channels=(Channels.bot_commands,), roles=STAFF_PARTNERS_COMMUNITY_ROLES)
    async def patreon_supporters(self, ctx: commands.Context) -> None:
        """Sends the current list of patreon supporters, sorted by tier level."""
        await self.send_current_supporters(ctx.channel)

    @tasks.loop(time=datetime.time(hour=17))
    async def current_monthly_supporters(self) -> None:
        """A loop running daily to see if it's the first of the month. If so call `self.send_current_supporters()`."""
        now = arrow.utcnow()
        if now.day == 1:
            meta_channel = await get_or_fetch_channel(self.bot, Channels.meta)
            await self.send_current_supporters(meta_channel, automatic=True)


async def setup(bot: Bot) -> None:
    """Load the Patreon cog."""
    await bot.add_cog(Patreon(bot))
