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
from discord.ext.commands import Cog, Context, group

from bot.bot import Bot
from bot.constants import Guild, Icons, NEGATIVE_REPLIES, POSITIVE_REPLIES, STAFF_ROLES
from bot.converters import Duration
from bot.pagination import LinePaginator
from bot.utils.checks import without_role_check
from bot.utils.scheduling import Scheduler
from bot.utils.time import humanize_delta, wait_until

log = logging.getLogger(__name__)

WHITELISTED_CHANNELS = Guild.reminder_whitelist
MAXIMUM_REMINDERS = 5


class Reminders(Scheduler, Cog):
    """Provide in-channel reminder functionality."""

    def __init__(self, bot: Bot):
        self.bot = bot
        super().__init__()

        self.bot.loop.create_task(self.reschedule_reminders())

    async def reschedule_reminders(self) -> None:
        """Get all current reminders from the API and reschedule them."""
        await self.bot.wait_until_guild_available()
        response = await self.bot.api_client.get(
            'bot/reminders',
            params={'active': 'true'}
        )

        now = datetime.utcnow()

        for reminder in response:
            is_valid, *_ = self.ensure_valid_reminder(reminder, cancel_task=False)
            if not is_valid:
                continue

            remind_at = isoparse(reminder['expiration']).replace(tzinfo=None)

            # If the reminder is already overdue ...
            if remind_at < now:
                late = relativedelta(now, remind_at)
                await self.send_reminder(reminder, late)
            else:
                self.schedule_task(reminder["id"], reminder)

    def ensure_valid_reminder(
        self,
        reminder: dict,
        cancel_task: bool = True
    ) -> t.Tuple[bool, discord.User, discord.TextChannel]:
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
            asyncio.create_task(self._delete_reminder(reminder['id'], cancel_task))

        return is_valid, user, channel

    @staticmethod
    async def _send_confirmation(
        ctx: Context,
        on_success: str,
        reminder_id: str,
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

    async def _scheduled_task(self, reminder: dict) -> None:
        """A coroutine which sends the reminder once the time is reached, and cancels the running task."""
        reminder_id = reminder["id"]
        reminder_datetime = isoparse(reminder['expiration']).replace(tzinfo=None)

        # Send the reminder message once the desired duration has passed
        await wait_until(reminder_datetime)
        await self.send_reminder(reminder)

        log.debug(f"Deleting reminder {reminder_id} (the user has been reminded).")
        await self._delete_reminder(reminder_id)

    async def _delete_reminder(self, reminder_id: str, cancel_task: bool = True) -> None:
        """Delete a reminder from the database, given its ID, and cancel the running task."""
        await self.bot.api_client.delete('bot/reminders/' + str(reminder_id))

        if cancel_task:
            # Now we can remove it from the schedule list
            self.cancel_task(reminder_id)

    async def _reschedule_reminder(self, reminder: dict) -> None:
        """Reschedule a reminder object."""
        log.trace(f"Cancelling old task #{reminder['id']}")
        self.cancel_task(reminder["id"])

        log.trace(f"Scheduling new task #{reminder['id']}")
        self.schedule_task(reminder["id"], reminder)

    async def send_reminder(self, reminder: dict, late: relativedelta = None) -> None:
        """Send the reminder."""
        is_valid, user, channel = self.ensure_valid_reminder(reminder)
        if not is_valid:
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

        await channel.send(
            content=user.mention,
            embed=embed
        )
        await self._delete_reminder(reminder["id"])

    @group(name="remind", aliases=("reminder", "reminders", "remindme"), invoke_without_command=True)
    async def remind_group(self, ctx: Context, expiration: Duration, *, content: str) -> None:
        """Commands for managing your reminders."""
        await ctx.invoke(self.new_reminder, expiration=expiration, content=content)

    @remind_group.command(name="new", aliases=("add", "create"))
    async def new_reminder(self, ctx: Context, expiration: Duration, *, content: str) -> t.Optional[discord.Message]:
        """
        Set yourself a simple reminder.

        Expiration is parsed per: http://strftime.org/
        """
        embed = discord.Embed()

        # If the user is not staff, we need to verify whether or not to make a reminder at all.
        if without_role_check(ctx, *STAFF_ROLES):

            # If they don't have permission to set a reminder in this channel
            if ctx.channel.id not in WHITELISTED_CHANNELS:
                embed.colour = discord.Colour.red()
                embed.title = random.choice(NEGATIVE_REPLIES)
                embed.description = "Sorry, you can't do that here!"

                return await ctx.send(embed=embed)

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
                embed.colour = discord.Colour.red()
                embed.title = random.choice(NEGATIVE_REPLIES)
                embed.description = "You have too many active reminders!"

                return await ctx.send(embed=embed)

        # Now we can attempt to actually set the reminder.
        reminder = await self.bot.api_client.post(
            'bot/reminders',
            json={
                'author': ctx.author.id,
                'channel_id': ctx.message.channel.id,
                'jump_url': ctx.message.jump_url,
                'content': content,
                'expiration': expiration.isoformat()
            }
        )

        now = datetime.utcnow() - timedelta(seconds=1)
        humanized_delta = humanize_delta(relativedelta(expiration, now))

        # Confirm to the user that it worked.
        await self._send_confirmation(
            ctx,
            on_success=f"Your reminder will arrive in {humanized_delta}!",
            reminder_id=reminder["id"],
            delivery_dt=expiration,
        )

        self.schedule_task(reminder["id"], reminder)

    @remind_group.command(name="list")
    async def list_reminders(self, ctx: Context) -> t.Optional[discord.Message]:
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
                (rem['content'], rem['expiration'], rem['id'])
                for rem in data
            ),
            key=itemgetter(1)
        )

        lines = []

        for content, remind_at, id_ in reminders:
            # Parse and humanize the time, make it pretty :D
            remind_datetime = isoparse(remind_at).replace(tzinfo=None)
            time = humanize_delta(relativedelta(remind_datetime, now))

            text = textwrap.dedent(f"""
            **Reminder #{id_}:** *expires in {time}* (ID: {id_})
            {content}
            """).strip()

            lines.append(text)

        embed = discord.Embed()
        embed.colour = discord.Colour.blurple()
        embed.title = f"Reminders for {ctx.author}"

        # Remind the user that they have no reminders :^)
        if not lines:
            embed.description = "No active reminders could be found."
            return await ctx.send(embed=embed)

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
        # Send the request to update the reminder in the database
        reminder = await self.bot.api_client.patch(
            'bot/reminders/' + str(id_),
            json={'expiration': expiration.isoformat()}
        )

        # Send a confirmation message to the channel
        await self._send_confirmation(
            ctx,
            on_success="That reminder has been edited successfully!",
            reminder_id=id_,
            delivery_dt=expiration,
        )

        await self._reschedule_reminder(reminder)

    @edit_reminder_group.command(name="content", aliases=("reason",))
    async def edit_reminder_content(self, ctx: Context, id_: int, *, content: str) -> None:
        """Edit one of your reminder's content."""
        # Send the request to update the reminder in the database
        reminder = await self.bot.api_client.patch(
            'bot/reminders/' + str(id_),
            json={'content': content}
        )

        # Parse the reminder expiration back into a datetime for the confirmation message
        expiration = isoparse(reminder['expiration']).replace(tzinfo=None)

        # Send a confirmation message to the channel
        await self._send_confirmation(
            ctx,
            on_success="That reminder has been edited successfully!",
            reminder_id=id_,
            delivery_dt=expiration,
        )
        await self._reschedule_reminder(reminder)

    @remind_group.command("delete", aliases=("remove", "cancel"))
    async def delete_reminder(self, ctx: Context, id_: int) -> None:
        """Delete one of your active reminders."""
        await self._delete_reminder(id_)
        await self._send_confirmation(
            ctx,
            on_success="That reminder has been deleted successfully!",
            reminder_id=id_,
            delivery_dt=None,
        )


def setup(bot: Bot) -> None:
    """Load the Reminders cog."""
    bot.add_cog(Reminders(bot))
