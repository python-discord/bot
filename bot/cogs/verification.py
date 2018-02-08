# coding=utf-8
from discord import Message, Object
from discord.ext.commands import AutoShardedBot, Context, command

from bot.constants import VERIFICATION_CHANNEL, VERIFIED_ROLE
from bot.decorators import in_channel, without_role


class Verification:
    """
    User verification
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    async def on_message(self, message: Message):
        if message.author.bot:
            return  # They're a bot, ignore

        ctx = await self.bot.get_context(message)  # type: Context

        if ctx.command is not None and ctx.command.name == "accept":
            return  # They didn't use a command, or they used a command that isn't the accept command

        if ctx.channel.id == VERIFICATION_CHANNEL:  # We're in the verification channel
            for role in ctx.author.roles:
                if role.id == VERIFIED_ROLE:
                    return  # They're already verified

            await ctx.send(
                f"{ctx.author.mention} Please type `self.accept()` to verify that you accept our rules, "
                f"and gain access to the rest of the server.",
                delete_after=10
            )
            await ctx.message.delete()

    @command(name="accept", hidden=True, aliases=["verify", "verified", "accepted", "accept()"])
    @without_role(VERIFIED_ROLE)
    @in_channel(VERIFICATION_CHANNEL)
    async def accept(self, ctx: Context):
        """
        Accept our rules and gain access to the rest of the server
        """

        await ctx.author.add_roles(Object(VERIFIED_ROLE), reason="Accepted the rules")
        await ctx.message.delete()


def setup(bot):
    bot.add_cog(Verification(bot))
    print("Cog loaded: Verification")
