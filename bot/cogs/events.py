import logging

from discord import Colour, Embed, Member, Object
from discord.ext.commands import (
    BadArgument, Bot, BotMissingPermissions,
    CommandError, CommandInvokeError, CommandNotFound,
    Context, NoPrivateMessage, UserInputError
)

from bot.cogs.modlog import ModLog
from bot.constants import (
    Channels, Colours, DEBUG_MODE,
    Guild, Icons, Keys,
    Roles, URLs
)
from bot.utils import chunks

log = logging.getLogger(__name__)

RESTORE_ROLES = (str(Roles.muted), str(Roles.announcements))


class Events:
    """No commands, just event handlers."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.headers = {"X-API-KEY": Keys.site_api}

    @property
    def mod_log(self) -> ModLog:
        return self.bot.get_cog("ModLog")

    async def send_updated_users(self, *users, replace_all=False):
        users = list(filter(lambda user: str(Roles.verified) in user["roles"], users))

        for chunk in chunks(users, 1000):
            response = None

            try:
                if replace_all:
                    response = await self.bot.http_session.post(
                        url=URLs.site_user_api,
                        json=chunk,
                        headers={"X-API-Key": Keys.site_api}
                    )
                else:
                    response = await self.bot.http_session.put(
                        url=URLs.site_user_api,
                        json=chunk,
                        headers={"X-API-Key": Keys.site_api}
                    )

                    await response.json()  # We do this to ensure we got a proper response from the site
            except Exception:
                if not response:
                    log.exception(f"Failed to send {len(chunk)} users")
                else:
                    text = await response.text()
                    log.exception(f"Failed to send {len(chunk)} users", extra={"body": text})
                break  # Stop right now, thank you very much

        result = {}

        if replace_all:
            response = None

            try:
                response = await self.bot.http_session.post(
                    url=URLs.site_user_complete_api,
                    headers={"X-API-Key": Keys.site_api}
                )

                result = await response.json()
            except Exception:
                if not response:
                    log.exception(f"Failed to send {len(chunk)} users")
                else:
                    text = await response.text()
                    log.exception(f"Failed to send {len(chunk)} users", extra={"body": text})

        return result

    async def send_delete_users(self, *users):
        try:
            response = await self.bot.http_session.delete(
                url=URLs.site_user_api,
                json=list(users),
                headers={"X-API-Key": Keys.site_api}
            )

            return await response.json()
        except Exception:
            log.exception(f"Failed to delete {len(users)} users")
            return {}

    async def get_user(self, user_id):
        response = await self.bot.http_session.get(
            url=URLs.site_user_api,
            params={"user_id": user_id},
            headers={"X-API-Key": Keys.site_api}
        )

        resp = await response.json()
        return resp["data"]

    async def has_active_mute(self, user_id: str) -> bool:
        """
        Check whether a user has any active mute infractions
        """

        response = await self.bot.http_session.get(
            URLs.site_infractions_user.format(
                user_id=user_id
            ),
            params={"hidden": "True"},
            headers=self.headers
        )
        infraction_list = await response.json()

        # Check for active mute infractions
        if not infraction_list:
            # Short circuit
            return False

        return any(
            infraction["active"] for infraction in infraction_list if infraction["type"].lower() == "mute"
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

        if hasattr(command, "on_error"):
            log.debug(f"Command {command} has a local error handler, ignoring.")
            return

        if isinstance(e, CommandNotFound) and not hasattr(ctx, "invoked_from_error_handler"):
            tags_get_command = self.bot.get_command("tags get")
            ctx.invoked_from_error_handler = True

            # Return to not raise the exception
            return await ctx.invoke(tags_get_command, tag_name=ctx.invoked_with)
        elif isinstance(e, BadArgument):
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
        raise e

    async def on_ready(self):
        users = []

        for member in self.bot.get_guild(Guild.id).members:  # type: Member
            roles = [str(r.id) for r in member.roles]  # type: List[int]

            users.append({
                "avatar": member.avatar_url_as(format="png"),
                "user_id": str(member.id),
                "roles": roles,
                "username": member.name,
                "discriminator": member.discriminator
            })

        if users:
            log.info(f"{len(users)} user roles to be updated")

            done = await self.send_updated_users(*users, replace_all=True)

            if any(done.values()):
                embed = Embed(
                    title="Users updated"
                )

                for key, value in done.items():
                    if value:
                        if key == "deleted_oauth":
                            key = "Deleted (OAuth)"
                        elif key == "deleted_jam_profiles":
                            key = "Deleted (Jammer Profiles)"
                        elif key == "deleted_responses":
                            key = "Deleted (Jam Form Responses)"
                        elif key == "jam_bans":
                            key = "Ex-Jammer Bans"
                        else:
                            key = key.title()

                        embed.add_field(
                            name=key, value=str(value)
                        )

                if not DEBUG_MODE:
                    await self.bot.get_channel(Channels.devlog).send(
                        embed=embed
                    )

    async def on_member_update(self, before: Member, after: Member):
        if (
                before.roles == after.roles
                and before.name == after.name
                and before.discriminator == after.discriminator
                and before.avatar == after.avatar):
            return

        before_role_names = [role.name for role in before.roles]  # type: List[str]
        after_role_names = [role.name for role in after.roles]  # type: List[str]
        role_ids = [str(r.id) for r in after.roles]  # type: List[str]

        log.debug(f"{before.display_name} roles changing from {before_role_names} to {after_role_names}")

        changes = await self.send_updated_users({
            "avatar": after.avatar_url_as(format="png"),
            "user_id": str(after.id),
            "roles": role_ids,
            "username": after.name,
            "discriminator": after.discriminator
        })

        log.debug(f"User {after.id} updated; changes: {changes}")

    async def on_member_join(self, member: Member):
        role_ids = [str(r.id) for r in member.roles]  # type: List[str]
        new_roles = []

        try:
            user_objs = await self.get_user(str(member.id))
        except Exception as e:
            log.exception("Failed to persist roles")

            await self.mod_log.send_log_message(
                Icons.crown_red, Colour(Colours.soft_red), "Failed to persist roles",
                f"```py\n{e}\n```",
                member.avatar_url_as(static_format="png")
            )
        else:
            if user_objs:
                old_roles = user_objs[0].get("roles", [])

                for role in RESTORE_ROLES:
                    if role in old_roles:
                        # Check for mute roles that were not able to be removed and skip if present
                        if role == str(Roles.muted) and not await self.has_active_mute(str(member.id)):
                            log.debug(
                                f"User {member.id} has no active mute infraction, "
                                "their leftover muted role will not be persisted"
                            )
                            continue

                        new_roles.append(Object(int(role)))

                for role in new_roles:
                    if str(role) not in role_ids:
                        role_ids.append(str(role.id))

        changes = await self.send_updated_users({
            "avatar": member.avatar_url_as(format="png"),
            "user_id": str(member.id),
            "roles": role_ids,
            "username": member.name,
            "discriminator": member.discriminator
        })

        log.debug(f"User {member.id} joined; changes: {changes}")

        if new_roles:
            await member.add_roles(
                *new_roles,
                reason="Roles restored"
            )

            await self.mod_log.send_log_message(
                Icons.crown_blurple, Colour.blurple(), "Roles restored",
                f"Restored {len(new_roles)} roles",
                member.avatar_url_as(static_format="png")
            )

    async def on_member_remove(self, member: Member):
        changes = await self.send_delete_users({
            "user_id": str(member.id)
        })

        log.debug(f"User {member.id} left; changes: {changes}")


def setup(bot):
    bot.add_cog(Events(bot))
    log.info("Cog loaded: Events")
