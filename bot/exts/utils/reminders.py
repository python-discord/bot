import random
import textwrap
import typing as t
from datetime import datetime, timezone
from operator import itemgetter

import discord
from botcore.utils import scheduling
from botcore.utils.scheduling import Scheduler
from dateutil.parser import isoparse
from discord.ext.commands import Cog, Context, Greedy, group

from bot.bot import Bot
from bot.constants import Guild, Icons, MODERATION_ROLES, POSITIVE_REPLIES, Roles, STAFF_PARTNERS_COMMUNITY_ROLES
from bot.converters import Duration, UnambiguousUser
from bot.log import get_logger
from bot.pagination import LinePaginator
from bot.utils import time
from bot.utils.checks import has_any_role_check, has_no_roles_check
from bot.utils.lock import lock_arg
from bot.utils.members import get_or_fetch_member
from bot.utils.messages import send_denial

log = get_logger(__name__)

LOCK_NAMESPACE = "reminder"
WHITELISTED_CHANNELS = Guild.reminder_whitelist
MAXIMUM_REMINDERS = 5

Mentionable = t.Union[discord.Member, discord.Role]
ReminderMention = t.Union[UnambiguousUser, discord.Role]


class Reminders(Cog):
    """Provide in-channel reminder functionality."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.scheduler = Scheduler(self.__class__.__name__)

    async def cog_unload(self) -> None:
        """Cancel scheduled tasks."""
        self.scheduler.cancel_all()

    async def cog_load(self) -> None:
        """Get all current reminders from the API and reschedule them."""
        await self.bot.wait_until_guild_available()
        response = await self.bot.api_client.get(
            'bot/reminders',
            params={'active': 'true'}
        )

        now = datetime.now(timezone.utc)

        for reminder in response:
            is_valid, *_ = self.ensure_valid_reminder(reminder)
            if not is_valid:
                continue

            remind_at = isoparse(reminder['expiration'])

            # If the reminder is already overdue ...
            if remind_at < now:
                await self.send_reminder(reminder, remind_at)
            else:
                self.schedule_reminder(reminder)

    def ensure_valid_reminder(self, reminder: dict) -> t.Tuple[bool, discord.TextChannel]:
        """Ensure reminder channel can be fetched otherwise delete the reminder."""
        channel = self.bot.get_channel(reminder['channel_id'])
        is_valid = True
        if not channel:
            is_valid = False
            log.info(
                f"Reminder {reminder['id']} invalid: "
                f"Channel {reminder['channel_id']}={channel}."
            )
            scheduling.create_task(self.bot.api_client.delete(f"bot/reminders/{reminder['id']}"))

        return is_valid, channel

    @staticmethod
    async def _send_confirmation(
        ctx: Context,
        on_success: str,
        reminder_id: t.Union[str, int]
    ) -> None:
        """Send an embed confirming the reminder change was made successfully."""
        embed = discord.Embed(
            description=on_success,
            colour=discord.Colour.green(),
            title=random.choice(POSITIVE_REPLIES)
        )

        footer_str = f"ID: {reminder_id}"

        embed.set_footer(text=footer_str)

        await ctx.send(embed=embed)

    @staticmethod
    async def _check_mentions(ctx: Context, mentions: t.Iterable[Mentionable]) -> t.Tuple[bool, str]:
        """
        Returns whether or not the list of mentions is allowed.

        Conditions:
        - Role reminders are Mods+
        - Reminders for other users are Helpers+

        If mentions aren't allowed, also return the type of mention(s) disallowed.
        """
        if await has_no_roles_check(ctx, *STAFF_PARTNERS_COMMUNITY_ROLES):
            return False, "members/roles"
        elif await has_no_roles_check(ctx, *MODERATION_ROLES):
            return all(isinstance(mention, (discord.User, discord.Member)) for mention in mentions), "roles"
        else:
            return True, ""

    @staticmethod
    async def validate_mentions(ctx: Context, mentions: t.Iterable[Mentionable]) -> bool:
        """
        Filter mentions to see if the user can mention, and sends a denial if not allowed.

        Returns whether or not the validation is successful.
        """
        mentions_allowed, disallowed_mentions = await Reminders._check_mentions(ctx, mentions)

        if not mentions or mentions_allowed:
            return True
        else:
            await send_denial(ctx, f"You can't mention other {disallowed_mentions} in your reminder!")
            return False

    async def get_mentionables(self, mention_ids: t.List[int]) -> t.Iterator[Mentionable]:
        """Converts Role and Member ids to their corresponding objects if possible."""
        guild = self.bot.get_guild(Guild.id)
        for mention_id in mention_ids:
            member = await get_or_fetch_member(guild, mention_id)
            if mentionable := (member or guild.get_role(mention_id)):
                yield mentionable

    def schedule_reminder(self, reminder: dict) -> None:
        """A coroutine which sends the reminder once the time is reached, and cancels the running task."""
        reminder_datetime = isoparse(reminder['expiration'])
        self.scheduler.schedule_at(reminder_datetime, reminder["id"], self.send_reminder(reminder))

    async def _edit_reminder(self, reminder_id: int, payload: dict) -> dict:
        """
        Edits a reminder in the database given the ID and payload.

        Returns the edited reminder.
        """
        # Send the request to update the reminder in the database
        reminder = await self.bot.api_client.patch(
            'bot/reminders/' + str(reminder_id),
            json=payload
        )
        return reminder

    async def _reschedule_reminder(self, reminder: dict) -> None:
        """Reschedule a reminder object."""
        log.trace(f"Cancelling old task #{reminder['id']}")
        self.scheduler.cancel(reminder["id"])

        log.trace(f"Scheduling new task #{reminder['id']}")
        self.schedule_reminder(reminder)

    @lock_arg(LOCK_NAMESPACE, "reminder", itemgetter("id"), raise_error=True)
    async def send_reminder(self, reminder: dict, expected_time: t.Optional[time.Timestamp] = None) -> None:
        """Send the reminder."""
        is_valid, channel = self.ensure_valid_reminder(reminder)
        if not is_valid:
            # No need to cancel the task too; it'll simply be done once this coroutine returns.
            return
        embed = discord.Embed()
        if expected_time:
            embed.colour = discord.Colour.red()
            embed.set_author(
                icon_url=Icons.remind_red,
                name="Sorry, your reminder should have arrived earlier!"
            )
        else:
            embed.colour = discord.Colour.og_blurple()
            embed.set_author(
                icon_url=Icons.remind_blurple,
                name="It has arrived!"
            )

        # Let's not use a codeblock to keep emojis and mentions working. Embeds are safe anyway.
        embed.description = f"Here's your reminder: {reminder['content']}"

        # Here the jump URL is in the format of base_url/guild_id/channel_id/message_id
        additional_mentions = ' '.join([
            mentionable.mention async for mentionable in self.get_mentionables(reminder["mentions"])
        ])

        jump_url = reminder.get("jump_url")
        embed.description += f"\n[Jump back to when you created the reminder]({jump_url})"
        partial_message = channel.get_partial_message(int(jump_url.split("/")[-1]))
        try:
            await partial_message.reply(content=f"{additional_mentions}", embed=embed)
        except discord.HTTPException as e:
            log.info(
                f"There was an error when trying to reply to a reminder invocation message, {e}, "
                "fall back to using jump_url"
            )
            await channel.send(content=f"<@{reminder['author']}> {additional_mentions}", embed=embed)

        log.debug(f"Deleting reminder #{reminder['id']} (the user has been reminded).")
        await self.bot.api_client.delete(f"bot/reminders/{reminder['id']}")

    @group(name="remind", aliases=("reminder", "reminders", "remindme"), invoke_without_command=True)
    async def remind_group(
        self, ctx: Context, mentions: Greedy[ReminderMention], expiration: Duration, *, content: t.Optional[str] = None
    ) -> None:
        """
        Commands for managing your reminders.

        The `expiration` duration of `!remind new` supports the following symbols for each unit of time:
        - years: `Y`, `y`, `year`, `years`
        - months: `m`, `month`, `months`
        - weeks: `w`, `W`, `week`, `weeks`
        - days: `d`, `D`, `day`, `days`
        - hours: `H`, `h`, `hour`, `hours`
        - minutes: `M`, `minute`, `minutes`
        - seconds: `S`, `s`, `second`, `seconds`

        For example, to set a reminder that expires in 3 days and 1 minute, you can do `!remind new 3d1M Do something`.
        """
        await self.new_reminder(ctx, mentions=mentions, expiration=expiration, content=content)

    @remind_group.command(name="new", aliases=("add", "create"))
    async def new_reminder(
        self, ctx: Context, mentions: Greedy[ReminderMention], expiration: Duration, *, content: t.Optional[str] = None
    ) -> None:
        """
        Set yourself a simple reminder.

        The `expiration` duration supports the following symbols for each unit of time:
        - years: `Y`, `y`, `year`, `years`
        - months: `m`, `month`, `months`
        - weeks: `w`, `W`, `week`, `weeks`
        - days: `d`, `D`, `day`, `days`
        - hours: `H`, `h`, `hour`, `hours`
        - minutes: `M`, `minute`, `minutes`
        - seconds: `S`, `s`, `second`, `seconds`

        For example, to set a reminder that expires in 3 days and 1 minute, you can do `!remind new 3d1M Do something`.
        """
        # If the user is not staff, partner or part of the python community,
        # we need to verify whether or not to make a reminder at all.
        if await has_no_roles_check(ctx, *STAFF_PARTNERS_COMMUNITY_ROLES):

            # If they don't have permission to set a reminder in this channel
            if ctx.channel.id not in WHITELISTED_CHANNELS:
                await send_denial(ctx, "Sorry, you can't do that here!")
                return

            # Get their current active reminders
            active_reminders = await self.bot.api_client.get(
                'bot/reminders',
                params={
                    'author__id': str(ctx.author.id)
                }
            )

            # Let's limit this, so we don't get 10 000
            # reminders from kip or something like that :P
            if len(active_reminders) > MAXIMUM_REMINDERS:
                await send_denial(ctx, "You have too many active reminders!")
                return

        # Remove duplicate mentions
        mentions = set(mentions)
        mentions.discard(ctx.author)

        # Filter mentions to see if the user can mention members/roles
        if not await self.validate_mentions(ctx, mentions):
            return

        mention_ids = [mention.id for mention in mentions]

        # If `content` isn't provided then we try to get message content of a replied message
        if not content:
            if reference := ctx.message.reference:
                if isinstance((resolved_message := reference.resolved), discord.Message):
                    content = resolved_message.content
            # If we weren't able to get the content of a replied message
            if content is None:
                await send_denial(ctx, "Your reminder must have a content and/or reply to a message.")
                return

            # If the replied message has no content (e.g. only attachments/embeds)
            if content == "":
                content = "See referenced message."

        # Now we can attempt to actually set the reminder.
        reminder = await self.bot.api_client.post(
            'bot/reminders',
            json={
                'author': ctx.author.id,
                'channel_id': ctx.message.channel.id,
                'jump_url': ctx.message.jump_url,
                'content': content,
                'expiration': expiration.isoformat(),
                'mentions': mention_ids,
            }
        )

        formatted_time = time.discord_timestamp(expiration, time.TimestampFormats.DAY_TIME)
        mention_string = f"Your reminder will arrive on {formatted_time}"

        if mentions:
            mention_string += f" and will mention {len(mentions)} other(s)"
        mention_string += "!"

        # Confirm to the user that it worked.
        await self._send_confirmation(
            ctx,
            on_success=mention_string,
            reminder_id=reminder["id"]
        )

        self.schedule_reminder(reminder)

    @remind_group.command(name="list")
    async def list_reminders(self, ctx: Context) -> None:
        """View a paginated embed of all reminders for your user."""
        # Get all the user's reminders from the database.
        data = await self.bot.api_client.get(
            'bot/reminders',
            params={'author__id': str(ctx.author.id)}
        )

        # Make a list of tuples so it can be sorted by time.
        reminders = sorted(
            (
                (rem['content'], rem['expiration'], rem['id'], rem['mentions'])
                for rem in data
            ),
            key=itemgetter(1)
        )

        lines = []

        for content, remind_at, id_, mentions in reminders:
            # Parse and humanize the time, make it pretty :D
            expiry = time.format_relative(remind_at)

            mentions = ", ".join([
                # Both Role and User objects have the `name` attribute
                mention.name async for mention in self.get_mentionables(mentions)
            ])
            mention_string = f"\n**Mentions:** {mentions}" if mentions else ""

            text = textwrap.dedent(f"""
            **Reminder #{id_}:** *expires {expiry}* (ID: {id_}){mention_string}
            {content}
            """).strip()

            lines.append(text)

        embed = discord.Embed()
        embed.colour = discord.Colour.og_blurple()
        embed.title = f"Reminders for {ctx.author}"

        # Remind the user that they have no reminders :^)
        if not lines:
            embed.description = "No active reminders could be found."
            await ctx.send(embed=embed)
            return

        # Construct the embed and paginate it.
        embed.colour = discord.Colour.og_blurple()

        await LinePaginator.paginate(
            lines,
            ctx, embed,
            max_lines=3,
            empty=True
        )

    @remind_group.group(name="edit", aliases=("change", "modify"), invoke_without_command=True)
    async def edit_reminder_group(self, ctx: Context) -> None:
        """
        Commands for modifying your current reminders.

        The `expiration` duration supports the following symbols for each unit of time:
        - years: `Y`, `y`, `year`, `years`
        - months: `m`, `month`, `months`
        - weeks: `w`, `W`, `week`, `weeks`
        - days: `d`, `D`, `day`, `days`
        - hours: `H`, `h`, `hour`, `hours`
        - minutes: `M`, `minute`, `minutes`
        - seconds: `S`, `s`, `second`, `seconds`

        For example, to edit a reminder to expire in 3 days and 1 minute, you can do `!remind edit duration 1234 3d1M`.
        """
        await ctx.send_help(ctx.command)

    @edit_reminder_group.command(name="duration", aliases=("time",))
    async def edit_reminder_duration(self, ctx: Context, id_: int, expiration: Duration) -> None:
        """
        Edit one of your reminder's expiration.

        The `expiration` duration supports the following symbols for each unit of time:
        - years: `Y`, `y`, `year`, `years`
        - months: `m`, `month`, `months`
        - weeks: `w`, `W`, `week`, `weeks`
        - days: `d`, `D`, `day`, `days`
        - hours: `H`, `h`, `hour`, `hours`
        - minutes: `M`, `minute`, `minutes`
        - seconds: `S`, `s`, `second`, `seconds`

        For example, to edit a reminder to expire in 3 days and 1 minute, you can do `!remind edit duration 1234 3d1M`.
        """
        await self.edit_reminder(ctx, id_, {'expiration': expiration.isoformat()})

    @edit_reminder_group.command(name="content", aliases=("reason",))
    async def edit_reminder_content(self, ctx: Context, id_: int, *, content: str) -> None:
        """Edit one of your reminder's content."""
        await self.edit_reminder(ctx, id_, {"content": content})

    @edit_reminder_group.command(name="mentions", aliases=("pings",))
    async def edit_reminder_mentions(self, ctx: Context, id_: int, mentions: Greedy[ReminderMention]) -> None:
        """Edit one of your reminder's mentions."""
        # Remove duplicate mentions
        mentions = set(mentions)
        mentions.discard(ctx.author)

        # Filter mentions to see if the user can mention members/roles
        if not await self.validate_mentions(ctx, mentions):
            return

        mention_ids = [mention.id for mention in mentions]
        await self.edit_reminder(ctx, id_, {"mentions": mention_ids})

    @lock_arg(LOCK_NAMESPACE, "id_", raise_error=True)
    async def edit_reminder(self, ctx: Context, id_: int, payload: dict) -> None:
        """Edits a reminder with the given payload, then sends a confirmation message."""
        if not await self._can_modify(ctx, id_):
            return
        reminder = await self._edit_reminder(id_, payload)

        # Send a confirmation message to the channel
        await self._send_confirmation(
            ctx,
            on_success="That reminder has been edited successfully!",
            reminder_id=id_,
        )
        await self._reschedule_reminder(reminder)

    @remind_group.command("delete", aliases=("remove", "cancel"))
    @lock_arg(LOCK_NAMESPACE, "id_", raise_error=True)
    async def delete_reminder(self, ctx: Context, id_: int) -> None:
        """Delete one of your active reminders."""
        if not await self._can_modify(ctx, id_):
            return

        await self.bot.api_client.delete(f"bot/reminders/{id_}")
        self.scheduler.cancel(id_)

        await self._send_confirmation(
            ctx,
            on_success="That reminder has been deleted successfully!",
            reminder_id=id_
        )

    async def _can_modify(self, ctx: Context, reminder_id: t.Union[str, int]) -> bool:
        """
        Check whether the reminder can be modified by the ctx author.

        The check passes when the user is an admin, or if they created the reminder.
        """
        if await has_any_role_check(ctx, Roles.admins):
            return True

        api_response = await self.bot.api_client.get(f"bot/reminders/{reminder_id}")
        if not api_response["author"] == ctx.author.id:
            log.debug(f"{ctx.author} is not the reminder author and does not pass the check.")
            await send_denial(ctx, "You can't modify reminders of other users!")
            return False

        log.debug(f"{ctx.author} is the reminder author and passes the check.")
        return True


async def setup(bot: Bot) -> None:
    """Load the Reminders cog."""
    await bot.add_cog(Reminders(bot))
