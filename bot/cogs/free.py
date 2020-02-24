import logging
from datetime import datetime
from operator import itemgetter

from discord import Colour, Embed, Member, utils
from discord.ext.commands import Cog, Context, command

from bot.bot import Bot
from bot.constants import Categories, Channels, Free, STAFF_ROLES
from bot.decorators import redirect_output

log = logging.getLogger(__name__)

TIMEOUT = Free.activity_timeout
RATE = Free.cooldown_rate
PER = Free.cooldown_per


class Free(Cog):
    """Tries to figure out which help channels are free."""

    PYTHON_HELP_ID = Categories.help_in_use

    @command(name="free", aliases=('f',))
    @redirect_output(destination_channel=Channels.bot_commands, bypass_roles=STAFF_ROLES)
    async def free(self, ctx: Context, user: Member = None, seek: int = 2) -> None:
        """
        Lists free help channels by likeliness of availability.

        seek is used only when this command is invoked in a help channel.
        You cannot override seek without mentioning a user first.

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

        # Iterate through all the help channels
        # to check latest activity
        for channel in python_help.channels:
            # Seek further back in the help channel
            # the command was invoked in
            if channel.id == ctx.channel.id:
                messages = await channel.history(limit=seek).flatten()
                msg = messages[seek - 1]
            # Otherwise get last message
            else:
                msg = await channel.history(limit=1).next()  # noqa: B305

            inactive = (datetime.utcnow() - msg.created_at).seconds
            if inactive > TIMEOUT:
                free_channels.append((inactive, channel))

        embed = Embed()
        embed.colour = Colour.blurple()
        embed.title = "**Looking for a free help channel?**"

        if user is not None:
            embed.description = f"**Hey {user.mention}!**\n\n"
        else:
            embed.description = ""

        # Display all potentially inactive channels
        # in descending order of inactivity
        if free_channels:
            # Sort channels in descending order by seconds
            # Get position in list, inactivity, and channel object
            # For each channel, add to embed.description
            sorted_channels = sorted(free_channels, key=itemgetter(0), reverse=True)

            for (inactive, channel) in sorted_channels[:3]:
                minutes, seconds = divmod(inactive, 60)
                if minutes > 59:
                    hours, minutes = divmod(minutes, 60)
                    embed.description += f"{channel.mention} **{hours}h {minutes}m {seconds}s** inactive\n"
                else:
                    embed.description += f"{channel.mention} **{minutes}m {seconds}s** inactive\n"

            embed.set_footer(text="Please confirm these channels are free before posting")
        else:
            embed.description = (
                "Doesn't look like any channels are available right now. "
                "You're welcome to check for yourself to be sure. "
                "If all channels are truly busy, please be patient "
                "as one will likely be available soon."
            )

        await ctx.send(embed=embed)


def setup(bot: Bot) -> None:
    """Load the Free cog."""
    bot.add_cog(Free())
