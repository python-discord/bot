import asyncio
import logging
import random
import textwrap
import typing as t
from datetime import datetime, timedelta
from operator import itemgetter

import discord
from dateutil.parser import isoparse
from dateutil.relativedelta import relativedelta
from discord.ext.commands import Cog, Context, Greedy, group

from bot.bot import Bot
from bot.constants import Guild, Icons, MODERATION_ROLES, POSITIVE_REPLIES, Roles, STAFF_ROLES
from bot.converters import Duration
from bot.pagination import LinePaginator
from bot.utils.checks import has_any_role_check, has_no_roles_check
from bot.utils.lock import lock_arg
from bot.utils.messages import send_denial
from bot.utils.scheduling import Scheduler
from bot.utils.time import humanize_delta

log = logging.getLogger(__name__)

LOCK_NAMESPACE = "reminder"
WHITELISTED_CHANNELS = Guild.reminder_whitelist
MAXIMUM_REMINDERS = 5

Mentionable = t.Union[discord.Member, discord.Role]


class Reminders(Cog):
    """Provide in-channel reminder functionality."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.scheduler = Scheduler(self.__class__.__name__)

        self.bot.loop.create_task(self.reschedule_reminders())

    def cog_unload(self) -> None:
        """Cancel scheduled tasks."""
        self.scheduler.cancel_all()

    async def reschedule_reminders(self) -> None:
        """Get all current reminders from the API and reschedule them."""
        await self.bot.wait_until_guild_available()
        response = await self.bot.api_client.get(
            'bot/reminders',
            params={'active': 'true'}
        )

        now = datetime.utcnow()

        for reminder in response:
            is_valid, *_ = self.ensure_valid_reminder(reminder)
            if not is_valid:
                continue

            remind_at = isoparse(reminder['expiration']).replace(tzinfo=None)

            # If the reminder is already overdue ...
            if remind_at < now:
                late = relativedelta(now, remind_at)
                await self.send_reminder(reminder, late)
            else:
                self.schedule_reminder(reminder)

    def ensure_valid_reminder(self, reminder: dict) -> t.Tuple[bool, discord.User, discord.TextChannel]:
        """Ensure reminder author and channel can be fetched otherwise delete the reminder."""
        user = self.bot.get_user(reminder['author'])
        channel = self.bot.get_channel(reminder['channel_id'])
        is_valid = True
        if not user or not channel:
            is_valid = False
            log.info(
                f"Reminder {reminder['id']} invalid: "
                f"User {reminder['author']}={user}, Channel {reminder['channel_id']}={channel}."
            )
            asyncio.create_task(self.bot.api_client.delete(f"bot/reminders/{reminder['id']}"))

        return is_valid, user, channel

    @staticmethod
    async def _send_confirmation(
        ctx: Context,
        on_success: str,
        reminder_id: t.Union[str, int],
        delivery_dt: t.Optional[datetime],
    ) -> None:
        """Send an embed confirming the reminder change was made successfully."""
        embed = discord.Embed()
        embed.colour = discord.Colour.green()
        embed.title = random.choice(POSITIVE_REPLIES)
        embed.description = on_success

        footer_str = f"ID: {reminder_id}"
        if delivery_dt:
            # Reminder deletion will have a `None` `delivery_dt`
            footer_str = f"{footer_str}, Due: {delivery_dt.strftime('%Y-%m-%dT%H:%M:%S')}"

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
        if await has_no_roles_check(ctx, *STAFF_ROLES):
            return False, "members/roles"
        elif await has_no_roles_check(ctx, *MODERATION_ROLES):
            return all(isinstance(mention, discord.Member) for mention in mentions), "roles"
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

    def get_mentionables(self, mention_ids: t.List[int]) -> t.Iterator[Mentionable]:
        """Converts Role and Member ids to their corresponding objects if possible."""
        guild = self.bot.get_guild(Guild.id)
        for mention_id in mention_ids:
            if (mentionable := (guild.get_member(mention_id) or guild.get_role(mention_id))):
                yield mentionable

    def schedule_reminder(self, reminder: dict) -> None:
        """A coroutine which sends the reminder once the time is reached, and cancels the running task."""
        reminder_datetime = isoparse(reminder['expiration']).replace(tzinfo=None)
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
    async def send_reminder(self, reminder: dict, late: relativedelta = None) -> None:
        """Send the reminder."""
        is_valid, user, channel = self.ensure_valid_reminder(reminder)
        if not is_valid:
            # No need to cancel the task too; it'll simply be done once this coroutine returns.
            return

        embed = discord.Embed()
        embed.colour = discord.Colour.blurple()
        embed.set_author(
            icon_url=Icons.remind_blurple,
            name="It has arrived!"
        )

        embed.description = f"Here's your reminder: `{reminder['content']}`."

        if reminder.get("jump_url"):  # keep backward compatibility
            embed.description += f"\n[Jump back to when you created the reminder]({reminder['jump_url']})"

        if late:
            embed.colour = discord.Colour.red()
            embed.set_author(
                icon_url=Icons.remind_red,
                name=f"Sorry it arrived {humanize_delta(late, max_units=2)} late!"
            )

        additional_mentions = ' '.join(
            mentionable.mention for mentionable in self.get_mentionables(reminder["mentions"])
        )

        await channel.send(content=f"{user.mention} {additional_mentions}", embed=embed)

        log.debug(f"Deleting reminder #{reminder['id']} (the user has been reminded).")
        await self.bot.api_client.delete(f"bot/reminders/{reminder['id']}")

    @group(name="remind", aliases=("reminder", "reminders", "remindme"), invoke_without_command=True)
    async def remind_group(
        self, ctx: Context, mentions: Greedy[Mentionable], expiration: Duration, *, content: str
    ) -> None:
        """Commands for managing your reminders."""
        await self.new_reminder(ctx, mentions=mentions, expiration=expiration, content=content)

    @remind_group.command(name="new", aliases=("add", "create"))
    async def new_reminder(
        self, ctx: Context, mentions: Greedy[Mentionable], expiration: Duration, *, content: str
    ) -> None:
        """
        Set yourself a simple reminder.

        Expiration is parsed per: http://strftime.org/
        """
        # If the user is not staff, we need to verify whether or not to make a reminder at all.
        if await has_no_roles_check(ctx, *STAFF_ROLES):

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

        now = datetime.utcnow() - timedelta(seconds=1)
        humanized_delta = humanize_delta(relativedelta(expiration, now))
        mention_string = f"Your reminder will arrive in {humanized_delta}"

        if mentions:
            mention_string += f" and will mention {len(mentions)} other(s)"
        mention_string += "!"

        # Confirm to the user that it worked.
        await self._send_confirmation(
            ctx,
            on_success=mention_string,
            reminder_id=reminder["id"],
            delivery_dt=expiration,
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

        now = datetime.utcnow()

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
            remind_datetime = isoparse(remind_at).replace(tzinfo=None)
            time = humanize_delta(relativedelta(remind_datetime, now))

            mentions = ", ".join(
                # Both Role and User objects have the `name` attribute
                mention.name for mention in self.get_mentionables(mentions)
            )
            mention_string = f"\n**Mentions:** {mentions}" if mentions else ""

            text = textwrap.dedent(f"""
            **Reminder #{id_}:** *expires in {time}* (ID: {id_}){mention_string}
            {content}
            """).strip()

            lines.append(text)

        embed = discord.Embed()
        embed.colour = discord.Colour.blurple()
        embed.title = f"Reminders for {ctx.author}"

        # Remind the user that they have no reminders :^)
        if not lines:
            embed.description = "No active reminders could be found."
            await ctx.send(embed=embed)
            return

        # Construct the embed and paginate it.
        embed.colour = discord.Colour.blurple()

        await LinePaginator.paginate(
            lines,
            ctx, embed,
            max_lines=3,
            empty=True
        )

    @remind_group.group(name="edit", aliases=("change", "modify"), invoke_without_command=True)
    async def edit_reminder_group(self, ctx: Context) -> None:
        """Commands for modifying your current reminders."""
        await ctx.send_help(ctx.command)

    @edit_reminder_group.command(name="duration", aliases=("time",))
    async def edit_reminder_duration(self, ctx: Context, id_: int, expiration: Duration) -> None:
        """
        Edit one of your reminder's expiration.

        Expiration is parsed per: http://strftime.org/
        """
        await self.edit_reminder(ctx, id_, {'expiration': expiration.isoformat()})

    @edit_reminder_group.command(name="content", aliases=("reason",))
    async def edit_reminder_content(self, ctx: Context, id_: int, *, content: str) -> None:
        """Edit one of your reminder's content."""
        await self.edit_reminder(ctx, id_, {"content": content})

    @edit_reminder_group.command(name="mentions", aliases=("pings",))
    async def edit_reminder_mentions(self, ctx: Context, id_: int, mentions: Greedy[Mentionable]) -> None:
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

        # Parse the reminder expiration back into a datetime
        expiration = isoparse(reminder["expiration"]).replace(tzinfo=None)

        # Send a confirmation message to the channel
        await self._send_confirmation(
            ctx,
            on_success="That reminder has been edited successfully!",
            reminder_id=id_,
            delivery_dt=expiration,
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
            reminder_id=id_,
            delivery_dt=None,
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


def setup(bot: Bot) -> None:
    """Load the Reminders cog."""
    bot.add_cog(Reminders(bot))
