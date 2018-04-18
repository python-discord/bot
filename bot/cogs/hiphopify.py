import logging

from discord import Colour, Embed, Member
from discord.ext.commands import AutoShardedBot, Context, command

from bot.constants import ADMIN_ROLE, MODERATOR_ROLE, OWNER_ROLE
from bot.constants import SITE_API_KEY
from bot.decorators import with_role

log = logging.getLogger(__name__)


class Hiphopify:
    """
    A set of commands to moderate terrible nicknames.
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot
        self.headers = {"X-API-KEY": SITE_API_KEY}

    async def on_member_update(self, before, after):
        """
        This event will trigger when someone changes their name.
        At this point we will look up the user in our database and check
        whether they are allowed o change their names, or if they are in
        hiphop-prison. If they are not allowed, we will change it back.
        :return:
        """

        pass

    @with_role(ADMIN_ROLE, OWNER_ROLE, MODERATOR_ROLE)
    @command(name="hiphopify()", aliases=["hiphopify", "force_nick()", "force_nick"])
    async def hiphopify(self, ctx: Context, user_mention: str, duration: int, forced_nick: str = None):
        """
        This command will force a random rapper name (like Lil' Wayne) to be the users
        nickname for a specified duration. If a forced_nick is provided, it will use that instead.

        :param ctx: Discord message context
        :param ta:
        If provided, this function shows data for that specific tag.
        If not provided, this function shows the caller a list of all tags.
        """

        pass

        # return await ctx.send(embed=embed)

    @with_role(ADMIN_ROLE, OWNER_ROLE, MODERATOR_ROLE)
    @command(name="unhiphopify()", aliases=["unhiphopify", "release_nick()", "release_nick"])
    async def unhiphopify(self, ctx: Context, member: Member):
        """
        This command will remove the entry from our database, allowing the user
        to once again change their nickname.

        :param ctx: Discord message context
        :param member: The member to unhiphopify
        """

        embed = Embed()
        embed.colour = Colour.red()
        embed.description = member.display_name

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Hiphopify(bot))
    log.info("Cog loaded: Hiphopify")
