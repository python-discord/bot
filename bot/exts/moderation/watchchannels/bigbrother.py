import textwrap
from collections import ChainMap

import discord
from discord import Interaction, Member, User, app_commands
from discord.ext.commands import Cog, Context, has_any_role

from bot.bot import Bot
from bot.constants import Channels, Guild, MODERATION_ROLES, Webhooks
from bot.converters import MemberOrUser
from bot.exts.moderation.infraction._utils import post_infraction
from bot.exts.moderation.watchchannels._watchchannel import WatchChannel
from bot.log import get_logger
from bot.utils.context_menus import authorise_command, authorise_context, context_menu_error_handler
from bot.utils.hybrid import hybrid_group

log = get_logger(__name__)

REASON_MAX_LENGTH = 1000


class WatchModal(discord.ui.Modal):
    """A modal asking for the reason to watch or unwatch a user."""

    reason = discord.ui.TextInput(label="Reason", style=discord.TextStyle.long, max_length=REASON_MAX_LENGTH)

    def __init__(self, ctx: Context, user: Member | User, *, watching: bool):
        super().__init__(title=f"{'Unwatch' if watching else 'Watch'} {user.display_name}"[:45])
        self.ctx = ctx
        self.user = user
        self.command_name = "bigbrother unwatch" if watching else "bigbrother watch"

    async def on_submit(self, interaction: Interaction) -> None:
        """Watch or unwatch the user through the same code as the command for it."""
        ctx = self.ctx
        # Respond to the modal submission rather than to the menu invocation.
        ctx.interaction = interaction

        # The menu was gated when it was invoked, but the roles of the invoker may have changed since.
        await authorise_context(ctx, self.command_name)

        # The work is only done after this, as the response to a modal must be sent within 3 seconds.
        await ctx.defer()
        await ctx.invoke(ctx.command, self.user, reason=self.reason.value.strip())

    async def on_error(self, interaction: Interaction, error: Exception) -> None:
        """Handle any exceptions in the processing of the modal."""
        await context_menu_error_handler(interaction, error)


class BigBrother(WatchChannel, Cog, name="Big Brother"):
    """Monitors users by relaying their messages to a watch channel to assist with moderation."""

    def __init__(self, bot: Bot) -> None:
        super().__init__(
            bot,
            destination=Channels.big_brother,
            webhook_id=Webhooks.big_brother.id,
            api_endpoint="bot/infractions",
            api_default_params={"active": "true", "type": "watch", "ordering": "-inserted_at", "limit": 10_000},
            logger=log
        )

        self.watch_menu = app_commands.ContextMenu(name="Watch / Unwatch", callback=self._watch_menu_callback)
        self.watch_menu.default_permissions = discord.Permissions.none()
        self.watch_menu.error(context_menu_error_handler)

    async def cog_load(self) -> None:
        """Add the context menu to the command tree, and load the watched users."""
        self.bot.tree.add_command(self.watch_menu, guild=discord.Object(Guild.id))
        await super().cog_load()

    async def cog_unload(self) -> None:
        """Remove the context menu from the command tree, and stop relaying messages."""
        self.bot.tree.remove_command(
            self.watch_menu.name,
            guild=discord.Object(Guild.id),
            type=self.watch_menu.type,
        )
        await super().cog_unload()

    @hybrid_group(name="bigbrother", aliases=("bb",), invoke_without_command=True)
    @has_any_role(*MODERATION_ROLES)
    async def bigbrother_group(self, ctx: Context) -> None:
        """Monitors users by relaying their messages to the Big Brother watch channel."""
        await ctx.send_help(ctx.command)

    @bigbrother_group.command(name="watched", aliases=("all", "list"))
    @app_commands.describe(
        oldest_first="Order the list by oldest watched",
        update_cache="Update the user cache using the API before listing the users",
    )
    @has_any_role(*MODERATION_ROLES)
    async def watched_command(
        self, ctx: Context, oldest_first: bool = False, update_cache: bool = True
    ) -> None:
        """
        Shows the users that are currently being monitored by Big Brother.

        The optional kwarg `oldest_first` can be used to order the list by oldest watched.

        The optional kwarg `update_cache` can be used to update the user
        cache using the API before listing the users.
        """
        await ctx.defer()
        await self.list_watched_users(ctx, oldest_first=oldest_first, update_cache=update_cache)

    @bigbrother_group.command(name="oldest")
    @app_commands.describe(update_cache="Update the user cache using the API before listing the users")
    @has_any_role(*MODERATION_ROLES)
    async def oldest_command(self, ctx: Context, update_cache: bool = True) -> None:
        """
        Shows Big Brother monitored users ordered by oldest watched.

        The optional kwarg `update_cache` can be used to update the user
        cache using the API before listing the users.
        """
        await ctx.invoke(self.watched_command, oldest_first=True, update_cache=update_cache)

    @bigbrother_group.command(name="watch", aliases=("w",), root_aliases=("watch",))
    @app_commands.describe(
        user="The user to watch",
        reason="Why the user is being watched, displayed when relaying their messages",
    )
    @has_any_role(*MODERATION_ROLES)
    async def watch_command(self, ctx: Context, user: MemberOrUser, *, reason: str) -> None:
        """
        Relay messages sent by the given `user` to the `#big-brother` channel.

        A `reason` for adding the user to Big Brother is required and will be displayed
        in the header when relaying messages of this user to the watchchannel.
        """
        await ctx.defer()
        await self.apply_watch(ctx, user, reason)

    @bigbrother_group.command(name="unwatch", aliases=("uw",), root_aliases=("unwatch",))
    @app_commands.describe(user="The user to stop watching", reason="Why the user is no longer being watched")
    @has_any_role(*MODERATION_ROLES)
    async def unwatch_command(self, ctx: Context, user: MemberOrUser, *, reason: str) -> None:
        """Stop relaying messages by the given `user`."""
        await ctx.defer()
        await self.apply_unwatch(ctx, user, reason)

    @app_commands.guild_only()
    async def _watch_menu_callback(self, interaction: Interaction, user: Member | User) -> None:
        """Ask for a reason to stop watching the user if they are watched, or to start watching them if not."""
        watching = user.id in self.watched_users
        # Gated in the same way as the `bigbrother watch` or `bigbrother unwatch` command.
        ctx = await authorise_command(interaction, "bigbrother unwatch" if watching else "bigbrother watch")
        await interaction.response.send_modal(WatchModal(ctx, user, watching=watching))

    async def apply_watch(self, ctx: Context, user: MemberOrUser, reason: str) -> None:
        """
        Add `user` to watched users and apply a watch infraction with `reason`.

        A message indicating the result of the operation is sent to `ctx`.
        The message will include `user`'s previous watch infraction history, if it exists.
        """
        if user.bot:
            await ctx.send(f":x: I'm sorry {ctx.author}, I'm afraid I can't do that. I only watch humans.")
            return

        if not await self.fetch_user_cache():
            await ctx.send(f":x: Updating the user cache failed, can't watch user {user.mention}")
            return

        if user.id in self.watched_users:
            await ctx.send(f":x: {user.mention} is already being watched.")
            return

        # discord.User instances don't have a roles attribute
        if hasattr(user, "roles") and any(role.id in MODERATION_ROLES for role in user.roles):
            await ctx.send(f":x: I'm sorry {ctx.author}, I'm afraid I can't do that. I must be kind to my masters.")
            return

        response = await post_infraction(ctx, user, "watch", reason, hidden=True, active=True)

        if response is not None:
            self.watched_users[user.id] = response
            msg = f":white_check_mark: Messages sent by {user.mention} will now be relayed to Big Brother."

            history = await self.bot.api_client.get(
                self.api_endpoint,
                params={
                    "user__id": str(user.id),
                    "active": "false",
                    "type": "watch",
                    "ordering": "-inserted_at"
                }
            )

            if len(history) > 1:
                total = f"({len(history) // 2} previous infractions in total)"
                end_reason = textwrap.shorten(history[0]["reason"], width=500, placeholder="...")
                start_reason = f"Watched: {textwrap.shorten(history[1]['reason'], width=500, placeholder='...')}"
                msg += f"\n\nUser's previous watch reasons {total}:```{start_reason}\n\n{end_reason}```"
        else:
            msg = ":x: Failed to post the infraction: response was empty."

        await ctx.send(msg)

    async def apply_unwatch(self, ctx: Context, user: MemberOrUser, reason: str, send_message: bool = True) -> None:
        """
        Remove `user` from watched users and mark their infraction as inactive with `reason`.

        If `send_message` is True, a message indicating the result of the operation is sent to
        `ctx`.
        """
        active_watches = await self.bot.api_client.get(
            self.api_endpoint,
            params=ChainMap(
                {"user__id": str(user.id)},
                self.api_default_params,
            )
        )
        if active_watches:
            log.trace("Active watches for user found.  Attempting to remove.")
            [infraction] = active_watches

            await self.bot.api_client.patch(
                f"{self.api_endpoint}/{infraction['id']}",
                json={"active": False}
            )

            await post_infraction(ctx, user, "watch", f"Unwatched: {reason}", hidden=True, active=False)

            self._remove_user(user.id)

            if not send_message:  # Prevents a message being sent to the channel if part of a permanent ban
                log.debug("Perma-banned user %s was unwatched.", user)
                return
            log.trace("User is not banned.  Sending message to channel")
            message = f":white_check_mark: Messages sent by {user.mention} will no longer be relayed."

        else:
            log.trace("No active watches found for user.")
            if not send_message:  # Prevents a message being sent to the channel if part of a permanent ban
                log.debug("%s was not on the watch list; no removal necessary.", user)
                return
            log.trace("User is not perma banned. Send the error message.")
            message = ":x: The specified user is currently not being watched."

        await ctx.send(message)


async def setup(bot: Bot) -> None:
    """Load the BigBrother cog."""
    await bot.add_cog(BigBrother(bot))
