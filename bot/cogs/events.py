import logging

from discord import Embed, Member
from discord.ext.commands import (
    AutoShardedBot, BadArgument, BotMissingPermissions,
    CommandError, CommandInvokeError, Context,
    NoPrivateMessage, UserInputError
)

from bot.constants import DEVLOG_CHANNEL, PYTHON_GUILD, SITE_API_KEY, SITE_API_URL
from bot.utils import chunks

log = logging.getLogger(__name__)


class Events:
    """
    No commands, just event handlers
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    async def send_updated_users(self, *users):
        try:
            response = await self.bot.http_session.post(
                url=f"{SITE_API_URL}/user",
                json=list(users),
                headers={"X-API-Key": SITE_API_KEY}
            )

            return await response.json()
        except Exception:
            log.exception(f"Failed to send role updates")
            return {}

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

        if hasattr(command, "error"):
            log.debug(f"Command {command} has a local error handler, ignoring.")
            return

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
        log.error(f"COMMAND ERROR: '{e}'")

    async def on_ready(self):
        users = []

        for member in self.bot.get_guild(PYTHON_GUILD).members:  # type: Member
            roles = [str(r.id) for r in member.roles]  # type: List[int]

            users.append({
                "user_id": str(member.id),
                "roles": roles,
                "username": member.name,
                "discriminator": member.discriminator
            })

        if users:
            log.debug(f"{len(users)} user roles to be updated")

            data = []  # type: List[dict]

            for chunk in chunks(users, 1000):
                data.append(await self.send_updated_users(*chunk))

            done = {}

            for item in data:
                for key, value in item.items():
                    if key not in done:
                        done[key] = value
                    else:
                        done[key] += value

            if any(done.values()):
                embed = Embed(
                    title="User roles updated"
                )

                for key, value in done.items():
                    if value:
                        embed.add_field(
                            name=key.title(), value=str(value)
                        )

                await self.bot.get_channel(DEVLOG_CHANNEL).send(
                    embed=embed
                )

    async def on_member_update(self, before: Member, after: Member):
        if before.roles == after.roles and before.name == after.name and before.discriminator == after.discriminator:
            return

        before_role_names = [role.name for role in before.roles]  # type: List[str]
        after_role_names = [role.name for role in after.roles]  # type: List[str]
        role_ids = [str(r.id) for r in after.roles]  # type: List[int]

        log.debug(f"{before.display_name} roles changing from {before_role_names} to {after_role_names}")

        await self.send_updated_users({
            "user_id": str(after.id),
            "roles": role_ids,
            "username": after.name,
            "discriminator": after.discriminator
        })


def setup(bot):
    bot.add_cog(Events(bot))
    log.info("Cog loaded: Events")
