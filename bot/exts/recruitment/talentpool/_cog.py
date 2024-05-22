import asyncio
import textwrap
from datetime import UTC, datetime
from io import StringIO

import discord
from async_rediscache import RedisCache
from discord import Color, Embed, Member, PartialMessage, RawReactionActionEvent, User, app_commands
from discord.ext import commands, tasks
from discord.ext.commands import BadArgument, Cog, Context, group, has_any_role
from pydis_core.site_api import ResponseCodeError
from pydis_core.utils.channel import get_or_fetch_channel
from pydis_core.utils.members import get_or_fetch_member
from sentry_sdk import new_scope

from bot.bot import Bot
from bot.constants import Bot as BotConfig, Channels, Emojis, Guild, MODERATION_ROLES, Roles, STAFF_ROLES
from bot.converters import MemberOrUser, UnambiguousMemberOrUser
from bot.exts.recruitment.talentpool._api import Nomination, NominationAPI
from bot.exts.recruitment.talentpool._review import Reviewer
from bot.log import get_logger
from bot.pagination import LinePaginator
from bot.utils import time

AUTOREVIEW_ENABLED_KEY = "autoreview_enabled"
REASON_MAX_CHARS = 1000

# The number of days that a user can have no activity (no messages sent)
# until they should be removed from the talentpool.
DAYS_UNTIL_INACTIVE = 45

log = get_logger(__name__)

class NominationContextModal(discord.ui.Modal, title="New Nomination"):
    nomination = discord.ui.TextInput(
        label="Additional nomination context:",
        style=discord.TextStyle.long,
        placeholder="Additional context for nomination...",
        required=False,
        # Take some length off for the URL that is going to be appended
        max_length=REASON_MAX_CHARS - 110
    )

    def __init__(self, cog: "TalentPool", message: discord.Message, noms_channel: discord.TextChannel):
        self.message = message
        self.api = cog.api
        self.noms_channel = noms_channel
        self.bot = cog.bot
        self.cog = cog

        super().__init__()

    async def on_submit(self, interaction: discord.Interaction) -> None:
        reason = ""

        if self.nomination.value and self.nomination.value != "":
            reason += f"{self.nomination.value}\n\n"

        reason += f"Nominated from: {self.message.jump_url}"

        try:
            await self.api.post_nomination(self.message.author.id, interaction.user.id, reason)
        except ResponseCodeError as e:
            match (e.status, e.response_json):
                case (400, {"user": _}):
                    await interaction.response.send_message(
                        f":x: {self.target.mention} can't be found in the database tables.",
                        ephemeral=True
                    )
                    log.warning(f"Could not find {self.target.author} in the site database tables, sync may be broken")
                    return

            raise e

        await interaction.response.send_message(
            f":white_check_mark: The nomination for {self.message.author.mention}"
            " has been added to the talent pool",
            ephemeral=True
        )

        noms_channel_message = (
            f":new: {interaction.user.mention} has nominated "
            f"{self.message.author.mention} from {self.message.jump_url}"
        )

        if self.nomination.value and self.nomination.value != "":
            noms_channel_message += "\n```\n"
            noms_channel_message += self.nomination.value
            noms_channel_message += "```"

        await self.noms_channel.send(noms_channel_message)

        await self.cog.maybe_relay_update(self.message.author.id, noms_channel_message)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Handle any exceptions in the processing of the modal."""
        await self.cog._nominate_context_error(interaction, error)

class TalentPool(Cog, name="Talentpool"):
    """Used to nominate potential helper candidates."""

    # RedisCache[str, bool]
    # Can contain a single key, "autoreview_enabled", with the value a bool indicating if autoreview is enabled.
    talentpool_settings = RedisCache()

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.api = NominationAPI(bot.api_client)
        self.reviewer = Reviewer(bot, self.api)
        # This lock lets us avoid cancelling the reviewer loop while the review code is running.
        self.autoreview_lock = asyncio.Lock()

        # Setup the context menu command for message-based nomination
        self.nominate_user_context_menu = app_commands.ContextMenu(
            name="Nominate User",
            callback=self._nominate_context_callback,
        )
        self.nominate_user_context_menu.default_permissions = discord.Permissions.none()
        self.nominate_user_context_menu.error(self._nominate_context_error)
        self.bot.tree.add_command(self.nominate_user_context_menu, guild=discord.Object(Guild.id))

    async def cog_load(self) -> None:
        """Start autoreview loop if enabled."""
        if await self.autoreview_enabled():
            self.autoreview_loop.start()

        self.prune_talentpool.start()

    async def autoreview_enabled(self) -> bool:
        """Return whether automatic posting of nomination reviews is enabled."""
        return await self.talentpool_settings.get(AUTOREVIEW_ENABLED_KEY, True)

    @group(name="talentpool", aliases=("tp", "talent", "nomination", "n"), invoke_without_command=True)
    @has_any_role(*STAFF_ROLES)
    async def nomination_group(self, ctx: Context) -> None:
        """Highlights the activity of helper nominees by relaying their messages to the talent pool channel."""
        await ctx.send_help(ctx.command)

    @nomination_group.group(name="autoreview", aliases=("ar",), invoke_without_command=True)
    @has_any_role(*MODERATION_ROLES)
    async def nomination_autoreview_group(self, ctx: Context) -> None:
        """Commands for enabling or disabling autoreview."""
        await ctx.send_help(ctx.command)

    @nomination_autoreview_group.command(name="enable", aliases=("on",))
    @has_any_role(Roles.admins)
    @commands.max_concurrency(1)
    async def autoreview_enable(self, ctx: Context) -> None:
        """
        Enable automatic posting of reviews.

        A review will be posted when the current number of active reviews is below the limit
        and long enough has passed since the last review.

        Users will be considered for review if they have been in the talent pool past a
        threshold time.

        The next user to review is chosen based on the number of nominations a user has,
        using the age of the first nomination as a tie-breaker (oldest first).
        """
        if await self.autoreview_enabled():
            await ctx.send(":x: Autoreview is already enabled.")
            return

        self.autoreview_loop.start()
        await self.talentpool_settings.set(AUTOREVIEW_ENABLED_KEY, True)
        await ctx.send(":white_check_mark: Autoreview enabled.")

    @nomination_autoreview_group.command(name="disable", aliases=("off",))
    @has_any_role(Roles.admins)
    @commands.max_concurrency(1)
    async def autoreview_disable(self, ctx: Context) -> None:
        """Disable automatic posting of reviews."""
        if not await self.autoreview_enabled():
            await ctx.send(":x: Autoreview is already disabled.")
            return

        # Only cancel the loop task when the autoreview code is not running
        async with self.autoreview_lock:
            self.autoreview_loop.cancel()

        await self.talentpool_settings.set(AUTOREVIEW_ENABLED_KEY, False)
        await ctx.send(":white_check_mark: Autoreview disabled.")

    @nomination_autoreview_group.command(name="status")
    @has_any_role(*MODERATION_ROLES)
    async def autoreview_status(self, ctx: Context) -> None:
        """Show whether automatic posting of reviews is enabled or disabled."""
        if await self.autoreview_enabled():
            await ctx.send("Autoreview is currently enabled.")
        else:
            await ctx.send("Autoreview is currently disabled.")

    @tasks.loop(hours=1)
    async def autoreview_loop(self) -> None:
        """Send request to `reviewer` to send a nomination if ready."""
        if not await self.autoreview_enabled():
            return

        async with self.autoreview_lock:
            log.info("Running check for users to nominate.")
            await self.reviewer.maybe_review_user()

    @tasks.loop(hours=24)
    async def prune_talentpool(self) -> None:
        """
        Prune any inactive users from the talentpool.

        A user is considered inactive if they have sent no messages on the server
        in the past `DAYS_UNTIL_INACTIVE` days.
        """
        log.info("Running task to prune users from talent pool")
        nominations = await self.api.get_nominations(active=True)

        if not nominations:
            return

        messages_per_user = await self.api.get_activity(
            [nomination.user_id for nomination in nominations],
            days=DAYS_UNTIL_INACTIVE
        )

        nomination_discussion = await get_or_fetch_channel(self.bot, Channels.nomination_discussion)
        for nomination in nominations:
            if messages_per_user[nomination.user_id] > 0:
                continue

            if nomination.reviewed:
                continue

            log.info("Removing %s from the talent pool due to inactivity", nomination.user_id)

            await nomination_discussion.send(
                f":warning: <@{nomination.user_id}> ({nomination.user_id})"
                " was removed from the talentpool as they have sent no messages"
                f" in the past {DAYS_UNTIL_INACTIVE} days."
            )
            await self.api.edit_nomination(
                nomination.id,
                active=False,
                end_reason=f"Automatic removal: User was inactive for more than {DAYS_UNTIL_INACTIVE}"
            )

    @nomination_group.group(
        name="list",
        aliases=("nominated", "nominees"),
        invoke_without_command=True
    )
    @has_any_role(*MODERATION_ROLES)
    async def list_group(
        self,
        ctx: Context,
    ) -> None:
        """
        Shows the users that are currently in the talent pool.

        The "Recent Nominations" sections shows users nominated in the past 7 days,
        so will not be considered for autoreview.

        In the "Autoreview Priority" section a :zzz: emoji will be shown next to
        users that have not been active recently enough to be considered for autoreview.
        Note that the order in this section will change over time so should not be relied upon.
        """
        await self.show_nominations_list(ctx, grouped_view=True)

    @list_group.command(name="oldest")
    async def list_oldest(self, ctx: Context) -> None:
        """Shows the users that are currently in the talent pool, ordered by oldest nomination."""
        await self.show_nominations_list(ctx, oldest_first=True)

    @list_group.command(name="newest")
    async def list_newest(self, ctx: Context) -> None:
        """Shows the users that are currently in the talent pool, ordered by newest nomination."""
        await self.show_nominations_list(ctx, oldest_first=False)

    async def show_nominations_list(
        self,
        ctx: Context,
        *,
        oldest_first: bool = False,
        grouped_view: bool = False,
    ) -> None:
        """
        Lists the currently nominated users.

        If `grouped_view` is passed, nominations will be displayed in the groups
        being reviewed, recent nominations, and others by autoreview priority.

        Otherwise, nominations will be sorted by age
        (ordered based on the value of `oldest_first`).
        """
        now = datetime.now(tz=UTC)
        nominations = await self.api.get_nominations(active=True)
        messages_per_user = await self.api.get_activity(
            [nomination.user_id for nomination in nominations],
            days=DAYS_UNTIL_INACTIVE
        )

        if grouped_view:
            reviewed_nominations = []
            recent_nominations = []
            other_nominations = []
            for nomination in nominations:
                if nomination.reviewed:
                    reviewed_nominations.append(nomination)
                elif not self.reviewer.is_nomination_old_enough(nomination, now):
                    recent_nominations.append(nomination)
                else:
                    other_nominations.append(nomination)

            other_nominations = await self.reviewer.sort_nominations_to_review(other_nominations, now)

            lines = [
                "**Being Reviewed:**",
                *await self.list_nominations(ctx, reviewed_nominations, messages_per_user),
                "**Recent Nominations:**",
                *await self.list_nominations(ctx, recent_nominations, messages_per_user),
                "**Other Nominations by Autoreview Priority:**",
                *await self.list_nominations(ctx, other_nominations, messages_per_user, show_inactive=True)
            ]
        else:
            if oldest_first:
                nominations.reverse()
            lines = await self.list_nominations(ctx, nominations, messages_per_user, show_reviewed=True)

            if not lines:
                lines = ["There are no active nominations"]

        embed = Embed(
            title="Talent Pool active nominations",
            color=Color.blue()
        )
        await LinePaginator.paginate(lines, ctx, embed, empty=False)

    async def list_nominations(
        self,
        ctx: Context,
        nominations: list[Nomination],
        messages_per_user: dict[int, int],
        *,
        show_reviewed: bool = False,
        show_inactive: bool = False,
    ) -> list[str]:
        """
        Formats the given nominations into a list.

        Pass `show_reviewed` to indicate reviewed nominations, and `show_inactive` to
        indicate if the user doesn't have recent enough activity to be autoreviewed.
        """
        lines: list[str] = []

        if not nominations:
            return ["*None*"]

        for nomination in nominations:
            line = f"- `{nomination.user_id}`"

            member = await get_or_fetch_member(ctx.guild, nomination.user_id)
            if member:
                line += f" ({member.name}#{member.discriminator})"
            else:
                line += " (not on server)"

            line += f", added {time.format_relative(nomination.inserted_at)}"

            if show_reviewed and nomination.reviewed:
                line += " *(reviewed)*"

            is_active = self.reviewer.is_user_active_enough(messages_per_user[nomination.user_id])
            if show_inactive and not is_active:
                line += " :zzz:"

            lines.append(line)
        return lines

    async def maybe_relay_update(self, nominee_id: int, update: str) -> None:
        """
        Checks for an active nomination thread for the user, if one is found relay the given update there.

        This is used to relay new nominations and nomination updates to active vote channels.
        """
        nomination = await self.api.get_active_nomination(nominee_id)

        if nomination and nomination.thread_id:
            log.debug(f"Found thread ID for {nominee_id} nomination, relaying new context.")
            thread = await get_or_fetch_channel(self.bot, nomination.thread_id)

            await thread.send(update)

    @nomination_group.command(
        name="forcenominate",
        aliases=("fw", "forceadd", "fa", "fn", "forcewatch"),
        root_aliases=("forcenominate",)
    )
    @has_any_role(*MODERATION_ROLES)
    async def force_nominate_command(self, ctx: Context, user: MemberOrUser, *, reason: str = "") -> None:
        """
        Adds the given `user` to the talent pool, from any channel.

        A `reason` for adding the user to the talent pool is optional.
        """
        await self._nominate_user(ctx, user, reason)

    @nomination_group.command(
        name="nominate",
        aliases=("nom", "n", "watch", "w", "add", "a"),
        root_aliases=("nominate", "nom")
    )
    @has_any_role(*STAFF_ROLES)
    async def nominate_command(self, ctx: Context, user: MemberOrUser, *, reason: str = "") -> None:
        """
        Adds the given `user` to the talent pool.

        A `reason` for adding the user to the talent pool is optional.
        This command can only be used in the `#nominations` channel.
        """
        if ctx.channel.id != Channels.nominations:
            if any(role.id in MODERATION_ROLES for role in ctx.author.roles):
                await ctx.send(
                    f":x: Nominations should be run in the <#{Channels.nominations}> channel. "
                    f"Use `{BotConfig.prefix}tp forcenominate` to override this check."
                )
            else:
                await ctx.send(f":x: Nominations must be run in the <#{Channels.nominations}> channel.")
            return

        await self._nominate_user(ctx, user, reason)

    @app_commands.checks.has_any_role(*STAFF_ROLES)
    async def _nominate_context_callback(self, interaction: discord.Interaction, message: discord.Message) -> None:
        """Create or update a nomination for the author of the selected message."""
        if message.author.bot:
            await interaction.response.send_message(
                ":x: I'm afraid I can't do that. Only humans can be nominated.",
                ephemeral=True
            )
            return

        if isinstance(message.author, Member) and any(role.id in STAFF_ROLES for role in message.author.roles):
            await interaction.response.send_message(
                ":x: Nominating staff members, eh? Here's a cookie :cookie:",
                ephemeral=True
            )
            return

        maybe_nom = await self.api.get_nomination_reason(message.author.id, interaction.user.id)

        if maybe_nom:
            nomination, reason = maybe_nom

            reason += f"\n\n{message.jump_url}"

            if len(reason) > REASON_MAX_CHARS:
                await interaction.response.send_message(
                    ":x: Cannot add additional context due to nomination reason character limit.",
                    ephemeral=True
                )
                return

            await self.api.edit_nomination_entry(
                nomination.id,
                actor_id=interaction.user.id,
                reason=reason
            )

            await interaction.response.send_message(
                ":white_check_mark: Existing nomination updated",
                ephemeral=True
            )

            await self.maybe_relay_update(
                message.author.id,
                f":new: {interaction.user.mention} has attached {message.jump_url} to their nomination"
            )

            return

        nominations_channel = self.bot.get_channel(Channels.nominations)

        await interaction.response.send_modal(NominationContextModal(self, message, nominations_channel))

    async def _nominate_context_error(
            self,
            interaction: discord.Interaction,
            error: app_commands.AppCommandError
    ) -> None:
        """Handle any errors that occur with the nomination context command."""
        if isinstance(error, app_commands.errors.MissingAnyRole):
            await interaction.response.send_message(
                ":x: You do not have permission to use this command", ephemeral=True
            )
            return

        message = (
            f":x: An unexpected error occured, Please let us know!\n\n"
            f"```{error.__class__.__name__}: {error}```"
        )

        if not interaction.response.is_done():
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.followup.send(message, ephemeral=True)

        with new_scope() as scope:
            scope.user = {
                "id": interaction.user.id,
                "username": str(interaction.user)
            }

            scope.set_tag("command", interaction.command.name)
            scope.set_extra("interaction_data", interaction.data)

            log.error(
                f"Error executing application command '{interaction.command.name}' invoked by {interaction.user}",
                exc_info=error
            )

    async def _nominate_user(self, ctx: Context, user: MemberOrUser, reason: str) -> None:
        """Adds the given user to the talent pool."""
        if user.bot:
            await ctx.send(f":x: I'm sorry {ctx.author}, I'm afraid I can't do that. Only humans can be nominated.")
            return

        if isinstance(user, Member) and any(role.id in STAFF_ROLES for role in user.roles):
            await ctx.send(":x: Nominating staff members, eh? Here's a cookie :cookie:")
            return

        if len(reason) > REASON_MAX_CHARS:
            await ctx.send(f":x: The reason's length must not exceed {REASON_MAX_CHARS} characters.")
            return

        try:
            await self.api.post_nomination(user.id, ctx.author.id, reason)
        except ResponseCodeError as e:
            match (e.status, e.response_json):
                case (400, {"user": _}):
                    await ctx.send(f":x: {user.mention} can't be found in the database tables.")
                    return
                case (400, {"actor": _}):
                    await ctx.send(f":x: You have already nominated {user.mention}.")
                    return
            raise

        await ctx.send(f"✅ The nomination for {user.mention} has been added to the talent pool.")

        thread_update = f":new: **{ctx.author.mention} has nominated {user.mention}"

        if reason:
            thread_update += f" with reason:** {reason}"
        else:
            thread_update += "**"

        await self.maybe_relay_update(user.id, thread_update)

    @nomination_group.command(name="history", aliases=("info", "search"))
    @has_any_role(*MODERATION_ROLES)
    async def history_command(self, ctx: Context, user: MemberOrUser) -> None:
        """Shows the specified user's nomination history."""
        result = await self.api.get_nominations(user.id, ordering="-active,-inserted_at")

        if not result:
            await ctx.send(f":warning: {user.mention} has never been nominated.")
            return

        embed = Embed(
            title=f"Nominations for {user.display_name} `({user.id})`",
            color=Color.blue()
        )
        lines = [await self._nomination_to_string(nomination) for nomination in result]
        await LinePaginator.paginate(
            lines,
            ctx=ctx,
            embed=embed,
            empty=True,
            max_lines=3,
            max_size=1000
        )

    @nomination_group.command(name="end", aliases=("unwatch", "unnominate"), root_aliases=("unnominate",))
    @has_any_role(*MODERATION_ROLES)
    async def end_nomination_command(self, ctx: Context, user: MemberOrUser, *, reason: str) -> None:
        """
        Ends the active nomination of the specified user with the given reason.

        Providing a `reason` is required.
        """
        if len(reason) > REASON_MAX_CHARS:
            await ctx.send(f":x: The reason's length must not exceed {REASON_MAX_CHARS} characters.")
            return

        if await self.end_nomination(user.id, reason):
            await ctx.send(f":white_check_mark: Successfully un-nominated {user.mention}.")
        else:
            await ctx.send(f":x: {user.mention} doesn't have an active nomination.")

    @nomination_group.group(name="append", aliases=("amend",), invoke_without_command=True)
    @has_any_role(*STAFF_ROLES)
    async def nomination_append_group(self, ctx: Context) -> None:
        """Commands to append additional text to nominations."""
        await ctx.send_help(ctx.command)

    @nomination_append_group.command(name="reason")
    @has_any_role(*STAFF_ROLES)
    async def append_reason_command(
        self,
        ctx: Context,
        nominee_or_nomination_id: UnambiguousMemberOrUser | int,
        nominator: UnambiguousMemberOrUser | None = None,
        *,
        reason: str
    ) -> None:
        """
        Append additional text to the nomination reason of a specific nominator for a given nomination.

        If nominee_or_nomination_id resolves to a member or user,
        append the text to the currently active nomination for that person.
        Otherwise, if it's an int, look up that nomination ID to edit.

        If no nominator is specified, assume the invoker is editing their own nomination reason.
        Otherwise, edit the reason from that specific nominator.

        Raise a permission error if a non-mod staff member invokes this command on a
        specific nomination ID, or with an nominator other than themselves.
        """
        # If not specified, assume the invoker is editing their own nomination reason.
        nominator = nominator or ctx.author

        if not any(role.id in MODERATION_ROLES for role in ctx.author.roles):
            if ctx.channel.id != Channels.nominations:
                await ctx.send(f":x: Nomination edits must be run in the <#{Channels.nominations}> channel.")
                return

            if nominator != ctx.author or isinstance(nominee_or_nomination_id, int):
                raise BadArgument(
                    "Only moderators can edit specific nomination IDs, "
                    "or the reason of a nominator other than themselves."
                )

        if not reason:
            await ctx.send(":x: You must include an additional reason when appending to an existing nomination.")

        if isinstance(nominee_or_nomination_id, int):
            nomination_id = nominee_or_nomination_id
            try:
                original_nomination = await self.api.get_nomination(nomination_id=nomination_id)
            except ResponseCodeError as e:
                match (e.status, e.response_json):
                    case (400, {"actor": _}):
                        await ctx.send(f":x: {nominator.mention} doesn't have an entry in this nomination.")
                        return
                    case (404, _):
                        await ctx.send(f":x: Can't find a nomination with id `{nomination_id}`.")
                        return
                raise

            nomination_entries = original_nomination.entries
        else:
            active_nominations = await self.api.get_nominations(user_id=nominee_or_nomination_id.id, active=True)
            if active_nominations:
                nomination_entries = active_nominations[0].entries
            else:
                await ctx.send(f":x: {nominee_or_nomination_id.mention} doesn't have an active nomination.")
                return

        old_reason = next((e.reason for e in nomination_entries if e.actor_id == nominator.id), None)

        if old_reason:
            add_period = not old_reason.endswith((".", "!", "?"))
            reason = old_reason + (". " if add_period else " ") + reason

        await self._edit_nomination_reason(
            ctx,
            target=nominee_or_nomination_id,
            actor=nominator,
            reason=reason
        )

    @nomination_group.group(name="edit", aliases=("e",), invoke_without_command=True)
    @has_any_role(*STAFF_ROLES)
    async def nomination_edit_group(self, ctx: Context) -> None:
        """Commands to edit nominations."""
        await ctx.send_help(ctx.command)

    @nomination_edit_group.command(name="reason")
    @has_any_role(*STAFF_ROLES)
    async def edit_reason_command(
        self,
        ctx: Context,
        nominee_or_nomination_id: UnambiguousMemberOrUser | int,
        nominator: UnambiguousMemberOrUser | None = None,
        *,
        reason: str
    ) -> None:
        """
        Edit the nomination reason of a specific nominator for a given nomination.

        If nominee_or_nomination_id resolves to a member or user, edit the currently active nomination for that person.
        Otherwise, if it's an int, look up that nomination ID to edit.

        If no nominator is specified, assume the invoker is editing their own nomination reason.
        Otherwise, edit the reason from that specific nominator.

        Raise a permission error if a non-mod staff member invokes this command on a
        specific nomination ID, or with an nominator other than themselves.
        """
        # If not specified, assume the invoker is editing their own nomination reason.
        nominator = nominator or ctx.author

        if not any(role.id in MODERATION_ROLES for role in ctx.author.roles):
            if ctx.channel.id != Channels.nominations:
                await ctx.send(f":x: Nomination edits must be run in the <#{Channels.nominations}> channel.")
                return

            if nominator != ctx.author or isinstance(nominee_or_nomination_id, int):
                # Invoker has specified another nominator, or a specific nomination id
                raise BadArgument(
                    "Only moderators can edit specific nomination IDs, "
                    "or the reason of a nominator other than themselves."
                )

        await self._edit_nomination_reason(
            ctx,
            target=nominee_or_nomination_id,
            actor=nominator,
            reason=reason
        )

    async def _edit_nomination_reason(
        self,
        ctx: Context,
        *,
        target: int | Member | User,
        actor: MemberOrUser,
        reason: str,
    ) -> None:
        """Edit a nomination reason in the database after validating the input."""
        if len(reason) > REASON_MAX_CHARS:
            await ctx.send(f":x: The reason's length must not exceed {REASON_MAX_CHARS} characters.")
            return

        if isinstance(target, int):
            nomination_id = target
        else:
            active_nominations = await self.api.get_nominations(user_id=target.id, active=True)
            if active_nominations:
                nomination_id = active_nominations[0].id
            else:
                await ctx.send(f":x: {target.mention} doesn't have an active nomination.")
                return

        log.trace(f"Changing reason for nomination with id {nomination_id} of actor {actor} to {reason!r}")

        try:
            nomination = await self.api.edit_nomination_entry(nomination_id, actor_id=actor.id, reason=reason)
        except ResponseCodeError as e:
            match (e.status, e.response_json):
                case (400, {"actor": _}):
                    await ctx.send(f":x: {actor.mention} doesn't have an entry in this nomination.")
                    return
                case (404, _):
                    await ctx.send(f":x: Can't find a nomination with id `{target}`.")
                    return
            raise

        await ctx.send(f":white_check_mark: Updated the nomination reason for <@{nomination.user_id}>.")

        thread_update = f":pencil: **{actor.mention} has edited their nomination:** {reason}"

        await self.maybe_relay_update(nomination.user_id, thread_update)

    @nomination_edit_group.command(name="end_reason")
    @has_any_role(*MODERATION_ROLES)
    async def edit_end_reason_command(self, ctx: Context, nomination_id: int, *, reason: str) -> None:
        """Edits the unnominate reason for the nomination with the given `id`."""
        if len(reason) > REASON_MAX_CHARS:
            await ctx.send(f":x: The reason's length must not exceed {REASON_MAX_CHARS} characters.")
            return

        log.trace(f"Changing end reason for nomination with id {nomination_id} to {reason!r}")
        try:
            nomination = await self.api.edit_nomination(nomination_id, end_reason=reason)
        except ResponseCodeError as e:
            match (e.status, e.response_json):
                case (400, {"end_reason": _}):
                    await ctx.send(f":x: Can't edit nomination with id `{nomination_id}` because it's still active.")
                    return
                case (404, _):
                    await ctx.send(f":x: Can't find a nomination with id `{nomination_id}`.")
                    return
            raise

        await ctx.send(f":white_check_mark: Updated the nomination end reason for <@{nomination.user_id}>.")

    @nomination_group.command(aliases=("gr",))
    @has_any_role(*MODERATION_ROLES)
    async def get_review(self, ctx: Context, user_id: int) -> None:
        """Get the user's review as a markdown file."""
        nominations = await self.api.get_nominations(user_id, active=True)
        if not nominations:
            await ctx.send(f":x: There doesn't appear to be an active nomination for {user_id}")
            return

        review, _, _, nominations = await self.reviewer.make_review(nominations[0])

        review_file = discord.File(StringIO(review), f"{user_id}_review.md")
        nominations_file = discord.File(StringIO("\n\n".join(nominations)), f"{user_id}_nominations.md")

        await ctx.send(files=[review_file, nominations_file])

    @nomination_group.command(aliases=("review",))
    @has_any_role(*MODERATION_ROLES)
    async def post_review(self, ctx: Context, user_id: int) -> None:
        """Post the automatic review for the user ahead of time."""
        nominations = await self.api.get_nominations(user_id, active=True)
        if not nominations:
            await ctx.send(f":x: There doesn't appear to be an active nomination for {user_id}")
            return

        nomination = nominations[0]
        if nomination.reviewed:
            await ctx.send(":x: This nomination was already reviewed, but here's a cookie :cookie:")
            return

        await self.reviewer.post_review(nomination)
        await ctx.message.add_reaction(Emojis.check_mark)

    @Cog.listener()
    async def on_member_ban(self, guild: Guild, user: MemberOrUser) -> None:
        """Remove `user` from the talent pool after they are banned."""
        if await self.end_nomination(user.id, "Automatic removal: User was banned"):
            nomination_discussion = await get_or_fetch_channel(self.bot, Channels.nomination_discussion)
            await nomination_discussion.send(
                f":warning: <@{user.id}> ({user.id})"
                " was removed from the talentpool due to being banned."
            )

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: RawReactionActionEvent) -> None:
        """
        Watch for reactions in the #nomination-voting channel to automate it.

        Adding an incident reaction will archive the message.
        """
        if payload.channel_id != Channels.nomination_voting:
            return

        if payload.user_id == self.bot.user.id:
            return

        message: PartialMessage = self.bot.get_channel(payload.channel_id).get_partial_message(payload.message_id)
        emoji = str(payload.emoji)

        if emoji in {Emojis.incident_actioned, Emojis.incident_unactioned}:
            log.info(f"Archiving nomination {message.id}")
            await self.reviewer.archive_vote(message, emoji == Emojis.incident_actioned)

    async def end_nomination(self, user_id: int, reason: str) -> bool:
        """End the active nomination of a user with the given reason and return True on success."""
        active_nominations = await self.api.get_nominations(user_id, active=True)

        if not active_nominations:
            log.debug(f"No active nomination exists for {user_id=}")
            return False

        log.info(f"Ending nomination: {user_id=} {reason=}")

        nomination = active_nominations[0]
        await self.api.edit_nomination(nomination.id, end_reason=reason, active=False)
        return True

    async def _nomination_to_string(self, nomination: Nomination) -> str:
        """Creates a string representation of a nomination."""
        guild = self.bot.get_guild(Guild.id)
        entries = []
        for entry in nomination.entries:
            actor = await get_or_fetch_member(guild, entry.actor_id)

            reason = entry.reason or "*None*"
            created = time.discord_timestamp(entry.inserted_at)
            entries.append(
                f"Actor: {actor.mention if actor else entry.actor_id}\nCreated: {created}\nReason: {reason}"
            )

        entries_string = "\n\n".join(entries)

        start_date = time.discord_timestamp(nomination.inserted_at)

        thread_jump_url = "*Not created*"

        if nomination.thread_id:
            try:
                thread = await get_or_fetch_channel(self.bot, nomination.thread_id)
            except discord.HTTPException:
                thread_jump_url = "*Not found*"
            else:
                thread_jump_url = f"[Jump to thread!]({thread.jump_url})"

        if nomination.active:
            lines = textwrap.dedent(
                f"""
                ===============
                Status: **Active**
                Date: {start_date}
                Nomination ID: `{nomination.id}`
                Nomination vote thread: {thread_jump_url}

                {entries_string}
                ===============
                """
            )
        else:
            end_date = time.discord_timestamp(nomination.ended_at)
            lines = textwrap.dedent(
                f"""
                ===============
                Status: Inactive
                Date: {start_date}
                Nomination ID: `{nomination.id}`
                Nomination vote thread: {thread_jump_url}

                {entries_string}

                End date: {end_date}
                Unnomination reason: {nomination.end_reason}
                ===============
                """
            )

        return lines.strip()

    async def cog_unload(self) -> None:
        """Cancels the autoreview loop on cog unload."""
        # Only cancel the loop task when the autoreview code is not running
        async with self.autoreview_lock:
            self.autoreview_loop.cancel()

        self.prune_talentpool.cancel()

        self.bot.tree.remove_command(
            self.nominate_user_context_menu.name,
            guild=discord.Object(Guild.id),
            type=self.nominate_user_context_menu.type
        )
