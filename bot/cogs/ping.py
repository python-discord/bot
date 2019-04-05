import logging
from discord.ext.commands import Bot, command, Context, BadArgument, MissingPermissions
from discord import Role, NotFound, Forbidden
from bot.decorators import with_role
from bot.constants import MODERATION_ROLES
from discord.utils import get

log = logging.getLogger(__name__)


class Ping:
    """
    Pinging a role so that there
    is no chance of it getting left un-pinged.
    Sorry guys <3 - aj
    """

    def __init__(self, bot: Bot):
        self.bot = bot

    @command()
    @with_role(*MODERATION_ROLES)
    async def announce(self, ctx: Context, role: Role, *, message: str):
        """
        Make an announcement that pings a role

        **`role`**: Accepts role mention, ID etc.
        **`message`**: The message that you want to ping the role with
        """
        if role.mentionable:
            await ctx.send("That role is already mentionable. Note: running this command will make it not mentionable.")
            pass

        await ctx.message.delete()
        await role.edit(mentionable=True)  # make the role ping-able
        await ctx.send(f"\n{role.mention}\n\n{message}")  # ping the role with the message
        await role.edit(mentionable=False)  # make the role un-ping-able
        return

    @announce.error
    async def announce_error(self, ctx: Context, error):
        if isinstance(error, BadArgument):
            await ctx.send("That's not a role in this guild!")
            return

        if isinstance(error.original, Forbidden):
            await ctx.send("I don't have permission to edit that role!")
            await ctx.send(f"Here is your message: ```{ctx.args[3]}```")
            return

        log.error(error)

    @command()
    @with_role(*MODERATION_ROLES)
    async def edit(self, ctx: Context, message_id: int, *, message_content: str):
        """
        Edits a message the bot has sent
        """
        msg = get(self.bot._connection._messages, id=message_id)  # check if message is in bot's cache
        if not msg:
            msg = await ctx.channel.fetch_message(id=message_id)  # call fetch_message

        await msg.edit(content=message_content)  # edit message with new content
        return

    @edit.error
    async def edit_error(self, ctx: Context, error):
        if isinstance(error.original, NotFound):
            await ctx.send("I can't find that message. Please check the ID.")
            return

        if isinstance(error.original, Forbidden):
            await ctx.send("For some reason I am forbidden from doing that.")

        log.error(error)

def setup(bot: Bot):
    bot.add_cog(Ping(bot))
    log.info("Cog loaded: Ping")
