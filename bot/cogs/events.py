# coding=utf-8
from aiohttp import ClientSession
from discord import Member, Embed
from discord.ext.commands import (
    AutoShardedBot, BadArgument, BotMissingPermissions,
    CommandError, CommandInvokeError, Context,
    NoPrivateMessage, UserInputError
)

from bot.constants import (
    SITE_API_KEY, SITE_API_USER_URL, PYTHON_GUILD, OWNER_ROLE, ADMIN_ROLE, MODERATOR_ROLE,
    DEVOPS_ROLE,
    DEVLOG_CHANNEL
)


class Events:
    """
    No commands, just event handlers
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    async def send_updated_users(self, *users):
        session = ClientSession(
            headers={"": SITE_API_KEY}
        )

        await session.post(
            url=SITE_API_USER_URL,
            json=list(users)
        )

    async def on_command_error(self, ctx: Context, e: CommandError):
        command = ctx.command
        parent = None

        if command is not None:
            parent = command.parent

        if parent and command:
            help_command = (self.bot.get_command("help"), parent.name, command.name)
        elif command:
            help_command = (self.bot.get_command("help"), command.name)
        else:
            help_command = (self.bot.get_command("help"),)

        if isinstance(e, BadArgument):
            await ctx.send(f"Bad argument: {e}\n")
            await ctx.invoke(*help_command)
        elif isinstance(e, UserInputError):
            await ctx.invoke(*help_command)
        elif isinstance(e, NoPrivateMessage):
            await ctx.send("Sorry, this command can't be used in a private message!")
        elif isinstance(e, BotMissingPermissions):
            await ctx.send(
                f"Sorry, it looks like I don't have the permissions I need to do that.\n\n"
                f"Here's what I'm missing: **{e.missing_perms}**"
            )
        elif isinstance(e, CommandInvokeError):
            await ctx.send(
                f"Sorry, an unexpected error occurred. Please let us know!\n\n```{e}```"
            )
            raise e.original
        print(e)

    async def on_ready(self):
        users = []

        for member in self.bot.get_guild(PYTHON_GUILD).members:  # type: Member
            roles = [r.id for r in member.roles]  # type: List[int]

            if OWNER_ROLE in roles:
                users.append({
                    "user_id": member.id,
                    "role": OWNER_ROLE
                })
            elif ADMIN_ROLE in roles:
                users.append({
                    "user_id": member.id,
                    "role": ADMIN_ROLE
                })
            elif MODERATOR_ROLE in roles:
                users.append({
                    "user_id": member.id,
                    "role": MODERATOR_ROLE
                })
            elif DEVOPS_ROLE in roles:
                users.append({
                    "user_id": member.id,
                    "role": DEVOPS_ROLE
                })

        if users:
            await self.send_updated_users(*users)
            await self.bot.get_channel(DEVLOG_CHANNEL).send(
                embed=Embed(
                    title="User roles updated", description=f"Updated {len(users)} users."
                )
            )

    async def on_member_update(self, before: Member, after: Member):
        if before.roles == after.roles:
            return

        roles = [r.id for r in after.roles]  # type: List[int]

        if OWNER_ROLE in roles:
            self.send_updated_users({
                "user_id": after.id,
                "role": OWNER_ROLE
            })
        elif ADMIN_ROLE in roles:
            self.send_updated_users({
                "user_id": after.id,
                "role": ADMIN_ROLE
            })
        elif MODERATOR_ROLE in roles:
            self.send_updated_users({
                "user_id": after.id,
                "role": MODERATOR_ROLE
            })
        elif DEVOPS_ROLE in roles:
            self.send_updated_users({
                "user_id": after.id,
                "role": DEVOPS_ROLE
            })


def setup(bot):
    bot.add_cog(Events(bot))
    print("Cog loaded: Events")
