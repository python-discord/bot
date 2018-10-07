import asyncio
import datetime
import logging
import random
import textwrap

from aiohttp import ClientResponseError
from dateutil.relativedelta import relativedelta
from discord import Colour, Embed
from discord.ext.commands import Bot, Context, group

from bot.constants import (
    Channels, Icons, Keys, NEGATIVE_REPLIES,
    POSITIVE_REPLIES, Roles, URLs
)
from bot.pagination import LinePaginator
from bot.utils.scheduling import Scheduler
from bot.utils.time import humanize_delta, parse_rfc1123, wait_until

log = logging.getLogger(__name__)

STAFF_ROLES = (Roles.owner, Roles.admin, Roles.moderator, Roles.helpers)
WHITELISTED_CHANNELS = (Channels.bot,)
MAXIMUM_REMINDERS = 5


class Reminders(Scheduler):

    def __init__(self, bot: Bot):
        self.bot = bot
        self.headers = {"X-API-Key": Keys.site_api}
        super().__init__()

    async def on_ready(self):
        # Get all the current reminders for re-scheduling
        response = await self.bot.http_session.get(
            url=URLs.site_reminders_api,
            headers=self.headers
        )

        response_data = await response.json()

        # Find the current time, timezone-aware.
        now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
        loop = asyncio.get_event_loop()

        for reminder in response_data["reminders"]:
            remind_at = parse_rfc1123(reminder["remind_at"])

            # If the reminder is already overdue ...
            if remind_at < now:
                late = relativedelta(now, remind_at)
                await self.send_reminder(reminder, late)

            else:
                self.schedule_task(loop, reminder["id"], reminder)

    @staticmethod
    async def _send_confirmation(ctx: Context, response: dict, on_success: str):
        """
        Send an embed confirming whether or not a change was made successfully.

        :return: A Boolean value indicating whether it failed (True) or passed (False)
        """

        embed = Embed()

        if not response.get("success"):
            embed.colour = Colour.red()
            embed.title = random.choice(NEGATIVE_REPLIES)
            embed.description = response.get("error_message", "An unexpected error occurred.")

            log.warn(f"Unable to create/edit/delete a reminder. Response: {response}")
            failed = True

        else:
            embed.colour = Colour.green()
            embed.title = random.choice(POSITIVE_REPLIES)
            embed.description = on_success

            failed = False

        await ctx.send(embed=embed)
        return failed

    async def _scheduled_task(self, reminder: dict):
        """
        A coroutine which sends the reminder once the time is reached.

        :param reminder: the data of the reminder.
        :return:
        """

        reminder_id = reminder["id"]
        reminder_datetime = parse_rfc1123(reminder["remind_at"])

        # Send the reminder message once the desired duration has passed
        await wait_until(reminder_datetime)
        await self.send_reminder(reminder)

        log.debug(f"Deleting reminder {reminder_id} (the user has been reminded).")
        await self._delete_reminder(reminder_id)

        # Now we can begone with it from our schedule list.
        self.cancel_task(reminder_id)

    async def _delete_reminder(self, reminder_id: str):
        """
        Delete a reminder from the database, given its ID.

        :param reminder_id: The ID of the reminder.
        """

        # The API requires a list, so let's give it one :)
        json_data = {
            "reminders": [
                reminder_id
            ]
        }

        await self.bot.http_session.delete(
            url=URLs.site_reminders_api,
            headers=self.headers,
            json=json_data
        )

        # Now we can remove it from the schedule list
        self.cancel_task(reminder_id)

    async def _reschedule_reminder(self, reminder):
        """
        Reschedule a reminder object.

        :param reminder: The reminder to be rescheduled.
        """

        loop = asyncio.get_event_loop()

        self.cancel_task(reminder["id"])
        self.schedule_task(loop, reminder["id"], reminder)

    async def send_reminder(self, reminder, late: relativedelta = None):
        """
        Send the reminder.

        :param reminder: The data about the reminder.
        :param late: How late the reminder is (if at all)
        """

        channel = self.bot.get_channel(int(reminder["channel_id"]))
        user = self.bot.get_user(int(reminder["user_id"]))

        embed = Embed()
        embed.colour = Colour.blurple()
        embed.set_author(
            icon_url=Icons.remind_blurple,
            name="It has arrived!"
        )

        embed.description = f"Here's your reminder: `{reminder['content']}`"

        if late:
            embed.colour = Colour.red()
            embed.set_author(
                icon_url=Icons.remind_red,
                name=f"Sorry it arrived {humanize_delta(late, max_units=2)} late!"
            )

        await channel.send(
            content=user.mention,
            embed=embed
        )
        await self._delete_reminder(reminder["id"])

    @group(name="remind", aliases=("reminder", "reminders"), invoke_without_command=True)
    async def remind_group(self, ctx: Context, duration: str, *, content: str):
        """
        Commands for managing your reminders.
        """

        await ctx.invoke(self.new_reminder, duration=duration, content=content)

    @remind_group.command(name="new", aliases=("add", "create"))
    async def new_reminder(self, ctx: Context, duration: str, *, content: str):
        """
        Set yourself a simple reminder.
        """

        embed = Embed()

        # Make sure the reminder should actually be made.
        if ctx.author.top_role.id not in STAFF_ROLES:

            # If they don't have permission to set a reminder in this channel
            if ctx.channel.id not in WHITELISTED_CHANNELS:
                embed.colour = Colour.red()
                embed.title = random.choice(NEGATIVE_REPLIES)
                embed.description = "Sorry, you can't do that here!"

                return await ctx.send(embed=embed)

            # Get their current active reminders
            response = await self.bot.http_session.get(
                url=URLs.site_reminders_user_api.format(user_id=ctx.author.id),
                headers=self.headers
            )

            active_reminders = await response.json()

            # Let's limit this, so we don't get 10 000
            # reminders from kip or something like that :P
            if len(active_reminders) > MAXIMUM_REMINDERS:
                embed.colour = Colour.red()
                embed.title = random.choice(NEGATIVE_REPLIES)
                embed.description = "You have too many active reminders!"

                return await ctx.send(embed=embed)

        # Now we can attempt to actually set the reminder.
        try:
            response = await self.bot.http_session.post(
                url=URLs.site_reminders_api,
                headers=self.headers,
                json={
                    "user_id": str(ctx.author.id),
                    "duration": duration,
                    "content": content,
                    "channel_id": str(ctx.channel.id)
                }
            )

            response_data = await response.json()

        # AFAIK only happens if the user enters, like, a quintillion weeks
        except ClientResponseError:
            embed.colour = Colour.red()
            embed.title = random.choice(NEGATIVE_REPLIES)
            embed.description = (
                "An error occurred while adding your reminder to the database. "
                "Did you enter a reasonable duration?"
            )

            log.warn(f"User {ctx.author} attempted to create a reminder for {duration}, but failed.")

            return await ctx.send(embed=embed)

        # Confirm to the user whether or not it worked.
        failed = await self._send_confirmation(
            ctx, response_data,
            on_success="Your reminder has been created successfully!"
        )

        # If it worked, schedule the reminder.
        if not failed:
            loop = asyncio.get_event_loop()
            reminder = response_data["reminder"]

            self.schedule_task(loop, reminder["id"], reminder)

    @remind_group.command(name="list")
    async def list_reminders(self, ctx: Context):
        """
        View a paginated embed of all reminders for your user.
        """

        # Get all the user's reminders from the database.
        response = await self.bot.http_session.get(
            url=URLs.site_reminders_user_api,
            params={"user_id": str(ctx.author.id)},
            headers=self.headers
        )

        data = await response.json()
        now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)

        # Make a list of tuples so it can be sorted by time.
        reminders = [
            (rem["content"], rem["remind_at"], rem["friendly_id"]) for rem in data["reminders"]
        ]

        reminders.sort(key=lambda rem: rem[1])

        lines = []

        for index, (content, remind_at, friendly_id) in enumerate(reminders):
            # Parse and humanize the time, make it pretty :D
            remind_datetime = parse_rfc1123(remind_at)
            time = humanize_delta(relativedelta(remind_datetime, now))

            text = textwrap.dedent(f"""
            **Reminder #{index}:** *expires in {time}* (ID: {friendly_id})
            {content}
            """).strip()

            lines.append(text)

        embed = Embed()
        embed.colour = Colour.blurple()
        embed.title = f"Reminders for {ctx.author}"

        # Remind the user that they have no reminders :^)
        if not lines:
            embed.description = "No active reminders could be found."
            return await ctx.send(embed=embed)

        # Construct the embed and paginate it.
        embed.colour = Colour.blurple()

        await LinePaginator.paginate(
            lines,
            ctx, embed,
            max_lines=3,
            empty=True
        )

    @remind_group.group(name="edit", aliases=("change", "modify"), invoke_without_command=True)
    async def edit_reminder_group(self, ctx: Context):
        """
        Commands for modifying your current reminders.
        """

        await ctx.invoke(self.bot.get_command("help"), "reminders", "edit")

    @edit_reminder_group.command(name="duration", aliases=("time",))
    async def edit_reminder_duration(self, ctx: Context, friendly_id: str, duration: str):
        """
        Edit one of your reminders' duration.
        """

        # Send the request to update the reminder in the database
        response = await self.bot.http_session.patch(
            url=URLs.site_reminders_user_api,
            headers=self.headers,
            json={
                "user_id": str(ctx.author.id),
                "friendly_id": friendly_id,
                "duration": duration
            }
        )

        # Send a confirmation message to the channel
        response_data = await response.json()
        failed = await self._send_confirmation(
            ctx, response_data,
            on_success="That reminder has been edited successfully!"
        )

        if not failed:
            await self._reschedule_reminder(response_data["reminder"])

    @edit_reminder_group.command(name="content", aliases=("reason",))
    async def edit_reminder_content(self, ctx: Context, friendly_id: str, *, content: str):
        """
        Edit one of your reminders' content.
        """

        # Send the request to update the reminder in the database
        response = await self.bot.http_session.patch(
            url=URLs.site_reminders_user_api,
            headers=self.headers,
            json={
                "user_id": str(ctx.author.id),
                "friendly_id": friendly_id,
                "content": content
            }
        )

        # Send a confirmation message to the channel
        response_data = await response.json()
        failed = await self._send_confirmation(
            ctx, response_data,
            on_success="That reminder has been edited successfully!"
        )

        if not failed:
            await self._reschedule_reminder(response_data["reminder"])

    @remind_group.command("delete", aliases=("remove",))
    async def delete_reminder(self, ctx: Context, friendly_id: str):
        """
        Delete one of your active reminders.
        """

        # Send the request to delete the reminder from the database
        response = await self.bot.http_session.delete(
            url=URLs.site_reminders_user_api,
            headers=self.headers,
            json={
                "user_id": str(ctx.author.id),
                "friendly_id": friendly_id
            }
        )

        response_data = await response.json()
        failed = await self._send_confirmation(
            ctx, response_data,
            on_success="That reminder has been deleted successfully!"
        )

        if not failed:
            self.cancel_reminder(response_data["reminder_id"])


def setup(bot: Bot):
    bot.add_cog(Reminders(bot))
    log.info("Cog loaded: Reminders")
