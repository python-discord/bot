import datetime

import arrow
import discord
from discord.ext import commands, tasks

from bot import constants, utils
from bot.bot import Bot
from bot.log import get_logger
from bot.utils.channel import get_or_fetch_channel
from bot.utils.members import has_role_id

log = get_logger(__name__)

PATREON_INFORMATION = (
    "Python Discord is not-for-profit and volunteer run, so we rely on Patreon donations to do what we do. "
    "We use the money we get to offer excellent prizes for all of our events. Prizes like t-shirts, "
    "stickers, microcontrollers that support CircuitPython, or maybe even a mechanical keyboard.\n\n"
    "You can read more about how Patreon donations help us, and consider donating yourself, on our patreon page "
    "[here](https://pydis.com/patreon)!"
)

# List of tuples containing tier number and Discord role ID.
# Ordered from highest tier to lowest.
PATREON_TIERS: list[tuple[int, int]] = [
    (3, constants.Roles.patreon_tier_3),
    (2, constants.Roles.patreon_tier_2),
    (1, constants.Roles.patreon_tier_1),
]


def get_patreon_tier(member: discord.Member) -> int:
    """
    Get the patreon tier of `member`.

    A patreon tier of 0 indicates the user is not a patreon.
    """
    for tier, role_id in PATREON_TIERS:
        if has_role_id(member, role_id):
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

        if not new_patreon_tier > old_patreon_tier:
            return

        message = (
            f":tada: {after.mention} just became a **tier {new_patreon_tier}** patron!\n"
            "[Support us on Patreon](https://pydis.com/patreon)"
        )
        channel = await utils.channel.get_or_fetch_channel(constants.Channels.meta)
        role = after.guild.get_role(new_patreon_tier)

        await channel.send(
            embed=discord.Embed(
                description=message,
                colour=role.colour,
            )
        )

    async def send_current_supporters(self, channel: discord.abc.Messageable) -> None:
        """Send the current list of patreon supporters, sorted by tier level."""
        guild = self.bot.get_guild(constants.Guild.id)

        embed_list = []
        for tier, role_id in PATREON_TIERS:
            role = guild.get_role(role_id)

            # Filter out any members where this is not their highest tier.
            patrons = [member for member in role.members if get_patreon_tier(member) == tier]
            patron_names = [f"{patron.mention} ({patron.name}#{patron.discriminator})" for patron in patrons]

            embed = discord.Embed(
                title=f"{role.name}",
                description="\n".join(patron_names),
                colour=role.colour
            )
            embed_list.append(embed)

        main_embed = discord.Embed(
            title="Patreon Supporters",
            description=(
                PATREON_INFORMATION +
                "\n\nThank you to the users listed below who are already supporting us!"
            ),
        )

        await channel.send(embeds=(main_embed, *embed_list))

    @commands.command("patrons")
    async def current_supporters_command(self, ctx: commands.Context) -> None:
        """Sends the current list of patreon supporters, sorted by tier level."""
        await self.send_current_supporters(ctx.channel)

    @tasks.loop(time=datetime.time(hour=17))
    async def current_monthly_supporters(self) -> None:
        """A loop running daily to see if it's the first of the month. If so call `self.send_current_supporters()`."""
        now = arrow.utcnow()
        if now.day == 1:
            meta_channel = await get_or_fetch_channel(constants.Channels.meta)
            await self.send_current_supporters(meta_channel)

    @commands.command("patreon")
    async def patreon_info(self, ctx: commands.Context) -> None:
        """Send information about how Python Discord uses Patreon."""
        await ctx.send(embed=discord.Embed(
            title="Patreon",
            description=PATREON_INFORMATION
        ))


async def setup(bot: Bot) -> None:
    """Load the Patreon cog."""
    await bot.add_cog(Patreon(bot))
