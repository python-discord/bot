import textwrap
from collections import ChainMap, defaultdict
from io import StringIO
from typing import Optional, Union

import discord
from async_rediscache import RedisCache
from discord import Color, Embed, Member, PartialMessage, RawReactionActionEvent, User
from discord.ext.commands import BadArgument, Cog, Context, group, has_any_role

from bot.api import ResponseCodeError
from bot.bot import Bot
from bot.constants import Channels, Emojis, Guild, MODERATION_ROLES, Roles, STAFF_ROLES
from bot.converters import MemberOrUser, UnambiguousMemberOrUser
from bot.exts.recruitment.talentpool._review import Reviewer
from bot.log import get_logger
from bot.pagination import LinePaginator
from bot.utils import scheduling, time
from bot.utils.members import get_or_fetch_member
from bot.utils.time import get_time_delta

AUTOREVIEW_ENABLED_KEY = "autoreview_enabled"
REASON_MAX_CHARS = 1000

log = get_logger(__name__)


class TalentPool(Cog, name="Talentpool"):
    """Used to nominate potential helper candidates."""

    # RedisCache[str, bool]
    # Can contain a single key, "autoreview_enabled", with the value a bool indicating if autoreview is enabled.
    talentpool_settings = RedisCache()

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.reviewer = Reviewer(self.__class__.__name__, bot, self)
        self.cache: Optional[defaultdict[dict]] = None
        self.api_default_params = {'active': 'true', 'ordering': '-inserted_at'}

        self.initial_refresh_task = scheduling.create_task(self.refresh_cache(), event_loop=self.bot.loop)
        scheduling.create_task(self.schedule_autoreviews(), event_loop=self.bot.loop)

    async def schedule_autoreviews(self) -> None:
        """Reschedule reviews for active nominations if autoreview is enabled."""
        if await self.autoreview_enabled():
            # Wait for a populated cache first
            await self.initial_refresh_task
            await self.reviewer.reschedule_reviews()
        else:
            log.trace("Not scheduling reviews as autoreview is disabled.")

    async def autoreview_enabled(self) -> bool:
        """Return whether automatic posting of nomination reviews is enabled."""
        return await self.talentpool_settings.get(AUTOREVIEW_ENABLED_KEY, True)

    async def refresh_cache(self) -> bool:
        """Updates TalentPool users cache."""
        # Wait until logged in to ensure bot api client exists
        await self.bot.wait_until_guild_available()
        try:
            data = await self.bot.api_client.get(
                'bot/nominations',
                params=self.api_default_params
            )
        except ResponseCodeError as err:
            log.exception("Failed to fetch the currently nominated users from the API", exc_info=err)
            return False

        self.cache = defaultdict(dict)

        for entry in data:
            user_id = entry.pop('user')
            self.cache[user_id] = entry

        return True

    @group(name='talentpool', aliases=('tp', 'talent', 'nomination', 'n'), invoke_without_command=True)
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
    async def autoreview_enable(self, ctx: Context) -> None:
        """
        Enable automatic posting of reviews.

        This will post reviews up to one day overdue. Older nominations can be
        manually reviewed with the `tp post_review <user_id>` command.
        """
        if await self.autoreview_enabled():
            await ctx.send(":x: Autoreview is already enabled")
            return

        await self.talentpool_settings.set(AUTOREVIEW_ENABLED_KEY, True)
        await self.reviewer.reschedule_reviews()
        await ctx.send(":white_check_mark: Autoreview enabled")

    @nomination_autoreview_group.command(name="disable", aliases=("off",))
    @has_any_role(Roles.admins)
    async def autoreview_disable(self, ctx: Context) -> None:
        """Disable automatic posting of reviews."""
        if not await self.autoreview_enabled():
            await ctx.send(":x: Autoreview is already disabled")
            return

        await self.talentpool_settings.set(AUTOREVIEW_ENABLED_KEY, False)
        self.reviewer.cancel_all()
        await ctx.send(":white_check_mark: Autoreview disabled")

    @nomination_autoreview_group.command(name="status")
    @has_any_role(*MODERATION_ROLES)
    async def autoreview_status(self, ctx: Context) -> None:
        """Show whether automatic posting of reviews is enabled or disabled."""
        if await self.autoreview_enabled():
            await ctx.send("Autoreview is currently enabled")
        else:
            await ctx.send("Autoreview is currently disabled")

    @nomination_group.command(
        name="nominees",
        aliases=("nominated", "all", "list", "watched"),
        root_aliases=("nominees",)
    )
    @has_any_role(*MODERATION_ROLES)
    async def list_command(
        self,
        ctx: Context,
        oldest_first: bool = False,
        update_cache: bool = True
    ) -> None:
        """
        Shows the users that are currently in the talent pool.

        The optional kwarg `oldest_first` can be used to order the list by oldest nomination.

        The optional kwarg `update_cache` can be used to update the user
        cache using the API before listing the users.
        """
        await self.list_nominated_users(ctx, oldest_first=oldest_first, update_cache=update_cache)

    async def list_nominated_users(
        self,
        ctx: Context,
        oldest_first: bool = False,
        update_cache: bool = True
    ) -> None:
        """
        Gives an overview of the nominated users list.

        It specifies the users' mention, name, how long ago they were nominated, and whether their
        review was scheduled or already posted.

        The optional kwarg `oldest_first` orders the list by oldest entry.

        The optional kwarg `update_cache` specifies whether the cache should
        be refreshed by polling the API.
        """
        successful_update = False
        if update_cache:
            if not (successful_update := await self.refresh_cache()):
                await ctx.send(":warning: Unable to update cache. Data may be inaccurate.")

        nominations = self.cache.items()
        if oldest_first:
            nominations = reversed(nominations)

        lines = []

        for user_id, user_data in nominations:
            member = await get_or_fetch_member(ctx.guild, user_id)
            line = f"• `{user_id}`"
            if member:
                line += f" ({member.name}#{member.discriminator})"
            inserted_at = user_data['inserted_at']
            line += f", added {get_time_delta(inserted_at)}"
            if not member:  # Cross off users who left the server.
                line = f"~~{line}~~"
            if user_data['reviewed']:
                line += " *(reviewed)*"
            elif user_id in self.reviewer:
                line += " *(scheduled)*"
            lines.append(line)

        if not lines:
            lines = ("There's nothing here yet.",)

        embed = Embed(
            title=f"Talent Pool active nominations ({'updated' if update_cache and successful_update else 'cached'})",
            color=Color.blue()
        )
        await LinePaginator.paginate(lines, ctx, embed, empty=False)

    @nomination_group.command(name='oldest')
    @has_any_role(*MODERATION_ROLES)
    async def oldest_command(self, ctx: Context, update_cache: bool = True) -> None:
        """
        Shows talent pool users ordered by oldest nomination.

        The optional kwarg `update_cache` can be used to update the user
        cache using the API before listing the users.
        """
        await ctx.invoke(self.list_command, oldest_first=True, update_cache=update_cache)

    @nomination_group.command(
        name="forcenominate",
        aliases=("fw", "forceadd", "fa", "fn", "forcewatch"),
        root_aliases=("forcenominate",)
    )
    @has_any_role(*MODERATION_ROLES)
    async def force_nominate_command(self, ctx: Context, user: MemberOrUser, *, reason: str = '') -> None:
        """
        Adds the given `user` to the talent pool, from any channel.

        A `reason` for adding the user to the talent pool is optional.
        """
        await self._nominate_user(ctx, user, reason)

    @nomination_group.command(name='nominate', aliases=("w", "add", "a", "watch"), root_aliases=("nominate",))
    @has_any_role(*STAFF_ROLES)
    async def nominate_command(self, ctx: Context, user: MemberOrUser, *, reason: str = '') -> None:
        """
        Adds the given `user` to the talent pool.

        A `reason` for adding the user to the talent pool is optional.
        This command can only be used in the `#nominations` channel.
        """
        if ctx.channel.id != Channels.nominations:
            if any(role.id in MODERATION_ROLES for role in ctx.author.roles):
                await ctx.send(
                    f":x: Nominations should be run in the <#{Channels.nominations}> channel. "
                    "Use `!tp forcenominate` to override this check."
                )
            else:
                await ctx.send(f":x: Nominations must be run in the <#{Channels.nominations}> channel")
            return

        await self._nominate_user(ctx, user, reason)

    async def _nominate_user(self, ctx: Context, user: MemberOrUser, reason: str) -> None:
        """Adds the given user to the talent pool."""
        if user.bot:
            await ctx.send(f":x: I'm sorry {ctx.author}, I'm afraid I can't do that. Only humans can be nominated.")
            return

        if isinstance(user, Member) and any(role.id in STAFF_ROLES for role in user.roles):
            await ctx.send(":x: Nominating staff members, eh? Here's a cookie :cookie:")
            return

        if not await self.refresh_cache():
            await ctx.send(f":x: Failed to update the cache; can't add {user}")
            return

        if len(reason) > REASON_MAX_CHARS:
            await ctx.send(f":x: Maxiumum allowed characters for the reason is {REASON_MAX_CHARS}.")
            return

        # Manual request with `raise_for_status` as False because we want the actual response
        session = self.bot.api_client.session
        url = self.bot.api_client._url_for('bot/nominations')
        kwargs = {
            'json': {
                'actor': ctx.author.id,
                'reason': reason,
                'user': user.id
            },
            'raise_for_status': False,
        }
        async with session.post(url, **kwargs) as resp:
            response_data = await resp.json()

            if resp.status == 400:
                if response_data.get('user', False):
                    await ctx.send(":x: The specified user can't be found in the database tables")
                elif response_data.get('actor', False):
                    await ctx.send(":x: You have already nominated this user")

                return
            else:
                resp.raise_for_status()

        self.cache[user.id] = response_data

        if await self.autoreview_enabled() and user.id not in self.reviewer:
            self.reviewer.schedule_review(user.id)

        msg = f"✅ The nomination for {user.mention} has been added to the talent pool"

        await ctx.send(msg)

    @nomination_group.command(name='history', aliases=('info', 'search'))
    @has_any_role(*MODERATION_ROLES)
    async def history_command(self, ctx: Context, user: MemberOrUser) -> None:
        """Shows the specified user's nomination history."""
        result = await self.bot.api_client.get(
            'bot/nominations',
            params={
                'user__id': str(user.id),
                'ordering': "-active,-inserted_at"
            }
        )
        if not result:
            await ctx.send(":warning: This user has never been nominated")
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
            await ctx.send(f":x: Maximum allowed characters for the end reason is {REASON_MAX_CHARS}.")
            return

        if await self.end_nomination(user.id, reason):
            await ctx.send(f":white_check_mark: Successfully un-nominated {user}")
        else:
            await ctx.send(":x: The specified user does not have an active nomination")

    @nomination_group.group(name='edit', aliases=('e',), invoke_without_command=True)
    @has_any_role(*STAFF_ROLES)
    async def nomination_edit_group(self, ctx: Context) -> None:
        """Commands to edit nominations."""
        await ctx.send_help(ctx.command)

    @nomination_edit_group.command(name='reason')
    @has_any_role(*STAFF_ROLES)
    async def edit_reason_command(
        self,
        ctx: Context,
        nominee_or_nomination_id: Union[UnambiguousMemberOrUser, int],
        nominator: Optional[UnambiguousMemberOrUser] = None,
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
                await ctx.send(f":x: Nomination edits must be run in the <#{Channels.nominations}> channel")
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
        target: Union[int, Member, User],
        actor: MemberOrUser,
        reason: str,
    ) -> None:
        """Edit a nomination reason in the database after validating the input."""
        if len(reason) > REASON_MAX_CHARS:
            await ctx.send(f":x: Maximum allowed characters for the reason is {REASON_MAX_CHARS}.")
            return
        if isinstance(target, int):
            nomination_id = target
        else:
            if nomination := self.cache.get(target.id):
                nomination_id = nomination["id"]
            else:
                await ctx.send("No active nomination found for that member.")
                return

        try:
            nomination = await self.bot.api_client.get(f"bot/nominations/{nomination_id}")
        except ResponseCodeError as e:
            if e.response.status == 404:
                log.trace(f"Nomination API 404: Can't find a nomination with id {nomination_id}")
                await ctx.send(f":x: Can't find a nomination with id `{nomination_id}`")
                return
            else:
                raise

        if not nomination["active"]:
            await ctx.send(":x: Can't edit the reason of an inactive nomination.")
            return

        if not any(entry["actor"] == actor.id for entry in nomination["entries"]):
            await ctx.send(f":x: {actor.mention} doesn't have an entry in this nomination.")
            return

        log.trace(f"Changing reason for nomination with id {nomination_id} of actor {actor} to {repr(reason)}")

        await self.bot.api_client.patch(
            f"bot/nominations/{nomination_id}",
            json={"actor": actor.id, "reason": reason}
        )
        await self.refresh_cache()  # Update cache
        await ctx.send(":white_check_mark: Successfully updated nomination reason.")

    @nomination_edit_group.command(name='end_reason')
    @has_any_role(*MODERATION_ROLES)
    async def edit_end_reason_command(self, ctx: Context, nomination_id: int, *, reason: str) -> None:
        """Edits the unnominate reason for the nomination with the given `id`."""
        if len(reason) > REASON_MAX_CHARS:
            await ctx.send(f":x: Maxiumum allowed characters for the end reason is {REASON_MAX_CHARS}.")
            return

        try:
            nomination = await self.bot.api_client.get(f"bot/nominations/{nomination_id}")
        except ResponseCodeError as e:
            if e.response.status == 404:
                log.trace(f"Nomination API 404: Can't find a nomination with id {nomination_id}")
                await ctx.send(f":x: Can't find a nomination with id `{nomination_id}`")
                return
            else:
                raise

        if nomination["active"]:
            await ctx.send(":x: Can't edit the end reason of an active nomination.")
            return

        log.trace(f"Changing end reason for nomination with id {nomination_id} to {repr(reason)}")

        await self.bot.api_client.patch(
            f"bot/nominations/{nomination_id}",
            json={"end_reason": reason}
        )
        await self.refresh_cache()  # Update cache.
        await ctx.send(":white_check_mark: Updated the end reason of the nomination!")

    @nomination_group.command(aliases=('mr',))
    @has_any_role(*MODERATION_ROLES)
    async def mark_reviewed(self, ctx: Context, user_id: int) -> None:
        """Mark a user's nomination as reviewed and cancel the review task."""
        if not await self.reviewer.mark_reviewed(ctx, user_id):
            return
        await ctx.send(f"{Emojis.check_mark} The user with ID `{user_id}` was marked as reviewed.")

    @nomination_group.command(aliases=('gr',))
    @has_any_role(*MODERATION_ROLES)
    async def get_review(self, ctx: Context, user_id: int) -> None:
        """Get the user's review as a markdown file."""
        review, _, _ = await self.reviewer.make_review(user_id)
        if review:
            file = discord.File(StringIO(review), f"{user_id}_review.md")
            await ctx.send(file=file)
        else:
            await ctx.send(f"There doesn't appear to be an active nomination for {user_id}")

    @nomination_group.command(aliases=('review',))
    @has_any_role(*MODERATION_ROLES)
    async def post_review(self, ctx: Context, user_id: int) -> None:
        """Post the automatic review for the user ahead of time."""
        if not await self.reviewer.mark_reviewed(ctx, user_id):
            return

        await self.reviewer.post_review(user_id, update_database=False)
        await ctx.message.add_reaction(Emojis.check_mark)

    @Cog.listener()
    async def on_member_ban(self, guild: Guild, user: Union[MemberOrUser]) -> None:
        """Remove `user` from the talent pool after they are banned."""
        await self.end_nomination(user.id, "User was banned.")

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: RawReactionActionEvent) -> None:
        """
        Watch for reactions in the #nomination-voting channel to automate it.

        Adding a ticket emoji will unpin the message.
        Adding an incident reaction will archive the message.
        """
        if payload.channel_id != Channels.nomination_voting:
            return

        message: PartialMessage = self.bot.get_channel(payload.channel_id).get_partial_message(payload.message_id)
        emoji = str(payload.emoji)

        if emoji == "\N{TICKET}":
            await message.unpin(reason="Admin task created.")
        elif emoji in {Emojis.incident_actioned, Emojis.incident_unactioned}:
            log.info(f"Archiving nomination {message.id}")
            await self.reviewer.archive_vote(message, emoji == Emojis.incident_actioned)

    async def end_nomination(self, user_id: int, reason: str) -> bool:
        """End the active nomination of a user with the given reason and return True on success."""
        active_nomination = await self.bot.api_client.get(
            'bot/nominations',
            params=ChainMap(
                {"user__id": str(user_id)},
                self.api_default_params,
            )
        )

        if not active_nomination:
            log.debug(f"No active nominate exists for {user_id=}")
            return False

        log.info(f"Ending nomination: {user_id=} {reason=}")

        nomination = active_nomination[0]
        await self.bot.api_client.patch(
            f"bot/nominations/{nomination['id']}",
            json={'end_reason': reason, 'active': False}
        )

        self.cache.pop(user_id)
        if await self.autoreview_enabled():
            self.reviewer.cancel(user_id)

        return True

    async def _nomination_to_string(self, nomination_object: dict) -> str:
        """Creates a string representation of a nomination."""
        guild = self.bot.get_guild(Guild.id)
        entries = []
        for site_entry in nomination_object["entries"]:
            actor_id = site_entry["actor"]
            actor = await get_or_fetch_member(guild, actor_id)

            reason = site_entry["reason"] or "*None*"
            created = time.format_infraction(site_entry["inserted_at"])
            entries.append(
                f"Actor: {actor.mention if actor else actor_id}\nCreated: {created}\nReason: {reason}"
            )

        entries_string = "\n\n".join(entries)

        active = nomination_object["active"]

        start_date = time.format_infraction(nomination_object["inserted_at"])
        if active:
            lines = textwrap.dedent(
                f"""
                ===============
                Status: **Active**
                Date: {start_date}
                Nomination ID: `{nomination_object["id"]}`

                {entries_string}
                ===============
                """
            )
        else:
            end_date = time.format_infraction(nomination_object["ended_at"])
            lines = textwrap.dedent(
                f"""
                ===============
                Status: Inactive
                Date: {start_date}
                Nomination ID: `{nomination_object["id"]}`

                {entries_string}

                End date: {end_date}
                Unnomination reason: {nomination_object["end_reason"]}
                ===============
                """
            )

        return lines.strip()

    def cog_unload(self) -> None:
        """Cancels all review tasks on cog unload."""
        super().cog_unload()
        self.reviewer.cancel_all()
