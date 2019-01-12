import logging
from datetime import datetime

from discord import Colour, Embed, Member, utils
from discord.ext import commands
from discord.ext.commands import BucketType, Context, command, cooldown

from bot.constants import Categories, Free, Roles


log = logging.getLogger(__name__)

TIMEOUT = Free.activity_timeout
RATE = Free.cooldown_rate
PER = Free.cooldown_per


class Free:
    """Tries to figure out which help channels are free."""

    PYTHON_HELP_ID = Categories.python_help

    @command(name="free", aliases=('f',))
    @cooldown(RATE, PER, BucketType.channel)
    async def free(self, ctx: Context, user: Member = None, seek: int = 2):
        """
        Lists free help channels by likeliness of availability.
        :param user: accepts user mention, ID, etc.
        :param seek: How far back to check the last active message.

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
                msg = messages[seek-1]
            # Otherwise get last message
            else:
                msg = await channel.history(limit=1).next()   # noqa (False positive)

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
            embed.description += "**The following channel{0} look{1} free:**\n\n**".format(
                's' if len(free_channels) > 1 else '',
                '' if len(free_channels) > 1 else 's'
            )

            # Sort channels in descending order by seconds
            # Get position in list, inactivity, and channel object
            # For each channel, add to embed.description
            for i, (inactive, channel) in enumerate(sorted(free_channels, reverse=True), 1):
                minutes, seconds = divmod(inactive, 60)
                if minutes > 59:
                    hours, minutes = divmod(minutes, 60)
                    embed.description += f"{i}. {channel.mention} inactive for {hours}h{minutes}m{seconds}s\n\n"
                else:
                    embed.description += f"{i}. {channel.mention} inactive for {minutes}m{seconds}s\n\n"

            embed.description += ("**\nThese channels aren't guaranteed to be free, "
                                  "so use your best judgement and check for yourself.")
        else:
            embed.description = ("**Doesn't look like any channels are available right now. "
                                 "You're welcome to check for yourself to be sure. "
                                 "If all channels are truly busy, please be patient "
                                 "as one will likely be available soon.**")

        await ctx.send(embed=embed)

    @free.error
    async def free_error(self, ctx: Context, error):
        """
        If error raised is CommandOnCooldown, and the
        user who invoked has the helper role, reset
        the cooldown and reinvoke the command.

        Otherwise log the error.
        """
        helpers = ctx.guild.get_role(Roles.helpers)

        if isinstance(error, commands.CommandOnCooldown):
            if helpers in ctx.author.roles:
                # reset cooldown so second invocation
                # doesn't bring us back here.
                ctx.command.reset_cooldown(ctx)
                # return to avoid needlessly logging the error
                return await ctx.reinvoke()

        log.exception(error)  # Don't ignore other errors


def setup(bot):
    bot.add_cog(Free())
    log.info("Cog loaded: Free")
