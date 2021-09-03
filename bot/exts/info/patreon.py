import logging

import discord
from discord.ext import commands

from bot import constants
from bot.bot import Bot

log = logging.getLogger(__name__)


class Patreon(commands.Cog):
    """Cog that shows patreon supporters."""

    def __init__(self, bot: Bot):
        self.bot: Bot = bot

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Send a message when someone receives a patreon role."""
        # Ensure the caches are up to date
        await self.bot.wait_until_guild_available()

        guild: discord.Guild = await self.bot.fetch_guild(constants.Guild.id)

        await guild.fetch_channels()
        await guild.fetch_roles()

        patreon_tier_1_role: discord.Role = guild.get_role(constants.Roles.patreon_tier_1)
        patreon_tier_2_role: discord.Role = guild.get_role(constants.Roles.patreon_tier_2)
        patreon_tier_3_role: discord.Role = guild.get_role(constants.Roles.patreon_tier_3)

        sending_channel = discord.utils.get(self.bot.get_all_channels(), id=constants.Channels.meta)

        current_patreon_tier: int = 0
        new_patreon_tier: int = 0

        # Both of these go from top to bottom to give the user their highest patreon role if they have multiple

        if patreon_tier_3_role in before.roles:
            current_patreon_tier = 3
        elif patreon_tier_2_role in before.roles:
            current_patreon_tier = 2
        elif patreon_tier_1_role in before.roles:
            current_patreon_tier = 1

        if patreon_tier_3_role in after.roles:
            new_patreon_tier = 3
            colour = patreon_tier_3_role.colour
        elif patreon_tier_2_role in after.roles:
            new_patreon_tier = 2
            colour = patreon_tier_2_role.colour
        elif patreon_tier_1_role in after.roles:
            new_patreon_tier = 1
            colour = patreon_tier_1_role.colour

        if not new_patreon_tier > current_patreon_tier:
            return

        message = (
            f":tada: {after.mention} just became a **tier {new_patreon_tier}** patron!\n"
            f"[Support us on Patreon](https://pydis.com/patreon)"
        )

        await sending_channel.send(
            embed=discord.Embed(
                description=message,
                colour=colour
            )
        )


def setup(bot: Bot) -> None:
    """Load the patreon cog."""
    bot.add_cog(Patreon(bot))
