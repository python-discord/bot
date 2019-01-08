import logging
from datetime import datetime

from discord import Colour, Embed, Member, utils
from discord.ext.commands import BucketType, Context, command, cooldown

from bot.constants import Categories


log = logging.getLogger(__name__)


class Free:
    """Tries to figure out which help channels are free."""

    PYTHON_HELP_ID = Categories.python_help
    TIME_INACTIVE = 300

    @command(name="free", aliases=('f',))
    @cooldown(1, 60.0, BucketType.channel)
    async def free(self, ctx: Context, user: Member = None, seek: int = 2):
        """
        Lists free help channels by likeliness of availability.
        :param user: accepts user mention, ID, etc.
        :param seek: How far back to check the last active message.

        seek is used only when this command is invoked in a help channel.

        When seek is 2, we are avoiding considering the last active message
        in a channel to be the one that invoked this command.

        When seek is 3 or more, a user has been mentioned on the assumption
        that they asked if the channel is free or they asked their question
        in an active channel, and we want the message before that happened.
        """
        free_channels = []
        python_help = utils.get(ctx.guild.categories, id=self.PYTHON_HELP_ID)

        if user is not None and seek == 2:
            seek = 3
        elif not 0 < seek < 10:
            seek = 3

        for channel in python_help.channels:
            if channel.id == ctx.channel.id:
                messages = await channel.history(limit=seek).flatten()
                msg = messages[seek-1]
            else:
                messages = await channel.history(limit=1).flatten()
                msg = messages[0]

            inactive = (datetime.utcnow() - msg.created_at).seconds
            if inactive > self.TIME_INACTIVE:
                free_channels.append((inactive, channel))

        embed = Embed()
        embed.colour = Colour.gold()
        embed.title = "**Looking for a free help channel?**"

        if user is not None:
            embed.description = f"**Hey {user.mention}!**\n\n"
        else:
            embed.description = ""

        if free_channels:
            embed.description += "**The following channel{0} look{1} free:**\n\n**".format(
                's' if len(free_channels) > 1 else '',
                '' if len(free_channels) > 1 else 's')

            for i, (inactive, channel) in enumerate(sorted(free_channels, reverse=True), 1):
                minutes, seconds = divmod(inactive, 60)
                if minutes > 60:
                    hours, minutes = divmod(minutes, 60)
                    embed.description += f"{i}. {channel.mention} inactive for {hours}h{minutes}m{seconds}s\n\n"
                else:
                    embed.description += f"{i}. {channel.mention} inactive for {minutes}m{seconds}s\n\n"

            embed.description += ("**\nThese channels aren't guaranteed to be free, "
                                  "so use your best judgement and check for yourself.")
        else:
            embed.description = ("**Doesn't look like any channels are available to me. "
                                 "You're welcome to check for yourself to be sure. "
                                 "If all channels are truly busy, please be patient "
                                 "as one will likely be available soon.**")

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Free())
    log.info("Cog loaded: Free")
