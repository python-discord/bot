import asyncio
import calendar
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import Callable, Optional, Tuple

from dateutil.parser import isoparse, parse
from dateutil.relativedelta import relativedelta
from discord import Embed, Guild, Member, Message, Reaction, Role, TextChannel, VoiceChannel
from discord.ext.commands import Cog, CommandInvokeError, Context, group, has_role

from bot.api import ResponseCodeError
from bot.bot import Bot
from bot.constants import Channels, Guild as Server, Roles
from bot.utils.scheduling import Scheduler
from bot.utils.time import humanize_delta

log = logging.getLogger(__name__)

EMOJIS = {
    "check": "✅",
    "cross": "❌"
}

DATE_PREFIX = {
    1: 'st', 21: 'st', 31: 'st',
    2: 'nd', 22: 'nd',
    3: 'rd', 23: 'rd'
}

NOT_SCHEDULED = "Not scheduled"
LIVE = "Live"


def is_event_organizer(func: Callable) -> Callable:
    """Check if the user is event organizer."""
    @wraps(func)
    async def wrapper(self: Cog, ctx: Context, event_name: str, *args, **kwargs) -> None:
        user_event = await self.bot.api_client.get(f"bot/user-events/{event_name}")

        if user_event["organizer"] != ctx.author.id:
            await ctx.send(f"You are not the organizer of the event **{event_name}**.")
            return

        await func(self, ctx, event_name, *args, **kwargs)

    return wrapper


class UserEvents(Cog):
    """Manage user events with the provided commands."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.scheduler = Scheduler(self.__class__.__name__)

        self.bot.loop.create_task(self.restart_event_reminders())

    def cog_unload(self) -> None:
        """Cancel scheduled tasks."""
        self.scheduler.cancel_all()

    async def restart_event_reminders(self) -> None:
        """Restart scheduled event reminders when bot restarts."""
        await self.bot.wait_until_guild_available()
        scheduled_events = await self.bot.api_client.get("bot/scheduled-events")

        for event in scheduled_events:
            # If event is live
            if datetime.now() > parse(event["start_time"]).replace(tzinfo=None):
                self.schedule_event_end_reminder(event)

            else:
                await self.schedule_event_start_reminder(event)

    @staticmethod
    def not_scheduled() -> str:
        """To indicate user event is not scheduled."""
        return "Not scheduled"

    @staticmethod
    def live() -> str:
        """To indicate user event is live."""
        return "Live"

    @staticmethod
    def scheduled(start_datetime: datetime, end_datetime: datetime) -> str:
        """
        To indicate user event is scheduled.

        The following code returns(an example):

        Scheduled on 7th November 2020,
        from 17:30 UTC To 18:00 UTC
        (24-hour format).
        """
        readable_date = (
            f"{start_datetime.day}{DATE_PREFIX.get(start_datetime.day, 'th')} "
            f"{list(calendar.month_name)[start_datetime.month]} {start_datetime.year}"
        )
        readable_time = (
            f"from {start_datetime.time().strftime('%H:%M')} UTC "
            f"To {end_datetime.time().strftime('%H:%M')} UTC\n(24-hour format)."
        )
        status = f"Scheduled on {readable_date},\n{readable_time}"
        return status

    @property
    def developers_role(self) -> Role:
        """Return guild developers role."""
        return self.guild.get_role(Roles.verified)

    @property
    def user_event_ongoing_role(self) -> Role:
        """Return guild user-event-ongoing role."""
        return self.guild.get_role(Roles.user_event_ongoing)

    @property
    def guild(self) -> Guild:
        """Return guild instance."""
        return self.bot.get_guild(Server.id)

    @property
    def user_event_coord_channel(self) -> TextChannel:
        """Return #user-events-coordinators channel."""
        return self.bot.get_channel(Channels.user_event_coordinators)

    @property
    def user_event_announcement_channel(self) -> TextChannel:
        """Return #user-events-announcement channel."""
        return self.bot.get_channel(Channels.user_event_announcements)

    @property
    def user_events_list_channel(self) -> TextChannel:
        """Return #user-events-list channel."""
        return self.bot.get_channel(Channels.user_event_list)

    @property
    def user_event_voice_channel(self) -> VoiceChannel:
        """Return #user-events-voice channel."""
        return self.bot.get_channel(Channels.user_event_voice)

    @staticmethod
    def user_event_embed(event_name: str, event_description: str, organizer: Member, status: str) -> Embed:
        """Embed representing a user event."""
        embed = Embed(
            title=f"{event_name}",
            description=(
                f"Organizer: {organizer.mention}\n\n"
                f"{event_description}\n\n"
                f"**Status:** {status}"
            )
        )
        return embed

    async def fetch_subscribers(self, message_id: int) -> list:
        """Fetch reacted users to event message as subscribers."""
        # Fetch the event message
        message = await self.user_events_list_channel.fetch_message(message_id)

        for reaction in message.reactions:
            # The `check` reaction will be added by the bot during event creation
            # So the chances of it being removed or not present is negligible

            if str(reaction) == EMOJIS["check"]:
                # Flatten into a list
                users = await reaction.users().flatten()
                return users

        return []

    async def update_user_event_message(self, status: str, user_event: dict) -> None:
        """Update event message on #user-events-list channel."""
        # Fetch user event message
        message = await self.user_events_list_channel.fetch_message(user_event["message_id"])

        embed = self.user_event_embed(
            user_event["name"],
            user_event["description"],
            self.guild.get_member(user_event["organizer"]),
            status
        )
        embed.set_footer(text="React to get notified about event start.")

        await message.edit(embed=embed)

    async def event_preparation(self, scheduled_event: dict) -> None:
        """Notify event organizer 30min before event and add User Event: Ongoing role."""
        organizer = self.guild.get_member(scheduled_event["user_event"]["organizer"])

        # Add the `user event: ongoing` role to the organizer
        await organizer.add_roles(self.user_event_ongoing_role)

        # Calculate remaining time for event start
        start_time = isoparse(scheduled_event["start_time"]).replace(tzinfo=None)
        time_remaining = humanize_delta(relativedelta(start_time, datetime.now()))

        await self.user_event_coord_channel.send(
            f"{organizer.mention} Event to start in {time_remaining}. "
            f"use `!userevent announce` "
            f"command to start the event."
        )

        self.schedule_event_end_reminder(scheduled_event)

    async def event_end(self, scheduled_event: dict) -> None:
        """End user event."""
        organizer = self.guild.get_member(scheduled_event["user_event"]["organizer"])

        # Remove the `user event: ongoing` role from the organizer
        await organizer.remove_roles(self.user_event_ongoing_role)

        status = NOT_SCHEDULED
        await self.update_user_event_message(status, scheduled_event["user_event"])

        # Close user events voice channel
        await self.edit_events_vc(open_vc=False)

        await self.user_event_coord_channel.send(f"{organizer.mention} event has ended! Voice channel is now closed.")

        # cancel the scheduler event and DELETE on site
        await self._cancel_scheduled_event(scheduled_event)

    async def schedule_event_start_reminder(self, scheduled_event: dict) -> None:
        """Schedule reminder to remind user 30min before event start."""
        start_datetime = isoparse(scheduled_event["start_time"]).replace(tzinfo=None)

        reminder = start_datetime - timedelta(minutes=30)

        # check if current time is already past reminder's time
        if reminder < datetime.now():
            await self.event_preparation(scheduled_event)
            return

        self.scheduler.schedule_at(
            reminder,
            scheduled_event["user_event"]["organizer"],
            self.event_preparation(scheduled_event)
        )

    def schedule_event_end_reminder(self, scheduled_event: dict) -> None:
        """Schedule reminder to remind user about event end."""
        reminder = isoparse(scheduled_event["end_time"]).replace(tzinfo=None)

        self.scheduler.schedule_at(
            reminder,
            scheduled_event["user_event"]["organizer"],
            self.event_end(scheduled_event)
        )

    async def send_confirmation_message(
            self,
            event_name: str,
            event_description: str,
            author: Member
    ) -> Tuple[Message, Embed]:
        """Send confirmation message for user event creation."""
        embed = self.user_event_embed(event_name, event_description, author, NOT_SCHEDULED)
        embed.set_footer(text="Confirm event creation.")

        message = await self.user_event_coord_channel.send(embed=embed)

        await message.add_reaction(EMOJIS["check"])
        await message.add_reaction(EMOJIS["cross"])

        return message, embed

    async def list_new_event(self, embed: Embed) -> Message:
        """List new event in the user-events-list channel."""
        embed.set_footer(text="React to be notified during event start.")

        # send event embed in #User-events-list channel
        event_message = await self.user_events_list_channel.send(embed=embed)

        # add reaction for subscribing
        await event_message.add_reaction(EMOJIS["check"])

        return event_message

    async def edit_events_vc(self, open_vc: bool) -> None:
        """Open/Close events voice channel."""
        await self.user_event_voice_channel.set_permissions(
            self.developers_role,
            view_channel=open_vc,
            connect=open_vc,
            speak=open_vc
        )

    async def _cancel_scheduled_event(self, scheduled_event: dict) -> None:
        """Cancel a scheduled event."""
        # Remove scheduler related to the scheduled event
        self.scheduler.cancel(scheduled_event["user_event"]["organizer"])

        # DELETE scheduled event on site
        await self.bot.api_client.delete(f"bot/scheduled-events/{scheduled_event['id']}")

        # Update user event status
        status = NOT_SCHEDULED
        await self.update_user_event_message(status, scheduled_event["user_event"])

        # Remove the `user event: ongoing` role from the organizer incase
        # the event is canceled using the cancel command when it is Live as
        # the organizer decides to stop the event early

        # It is not required to use the cancel command to stop the event though,
        # the ending timer, when done, will remove the role anyway
        organizer = self.guild.get_member(scheduled_event["user_event"]["organizer"])

        await organizer.remove_roles(self.user_event_ongoing_role)

    @group(name="userevent", invoke_without_command=True)
    async def user_event(self, ctx: Context) -> None:
        """Commands to perform CRUD operations on user events and scheduled events."""
        await ctx.send_help(ctx.command)

    @user_event.command(name="create")
    async def create_user_event(self, ctx: Context, event_name: str, *, event_description: str) -> None:
        """Create a new user event."""
        organizer = ctx.author.id

        # Ask user to confirm before event creation
        confirmation_message, embed = await self.send_confirmation_message(event_name, event_description, ctx.author)

        def check(reaction: Reaction, user: Member) -> bool:
            """Check for correct reaction and user."""
            return (
                user == ctx.author and str(reaction.emoji) in EMOJIS.values()
                and reaction.message.id == confirmation_message.id
            )

        # Check if user is OK for event creation
        try:
            choice, _ = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await self.user_event_coord_channel.send("User Event not created.")
            return

        # User reacting to `cross` indicates cancellation of event creation process.
        if str(choice) == EMOJIS["cross"]:
            await ctx.send("User Event not created.")
            return

        # POST new user event
        post_data = {
            "name": event_name,
            "organizer": organizer,
            "description": event_description,
            "message_id": 0  # patch message_id after sending message in user_events channel
        }
        await self.bot.api_client.post("bot/user-events", data=post_data)

        # List new event in user-events-list channel
        message = await self.list_new_event(embed)

        # PATCH message id of newly created user event
        patch_data = {
            "message_id": message.id
        }
        await self.bot.api_client.patch(f"bot/user-events/{event_name}", data=patch_data)

        await ctx.send(f"User Event **{event_name}** created.")

    @user_event.command(name="change_desc", aliases=["cd", "desc"])
    @is_event_organizer
    async def change_description(self, ctx: Context, event_name: str, *, event_description: str) -> None:
        """Change user event description."""
        data = {
            "description": event_description
        }
        # Patch event description
        # This is raise 404 error if event does not exist
        user_event = await self.bot.api_client.patch(
            f"bot/user-events/{event_name}",
            data=data
        )

        # Update event message
        # Check if event is scheduled
        query_params = {
            "user_event__organizer": ctx.author.id
        }
        scheduled_event = await self.bot.api_client.get(
            "bot/scheduled-events",
            params=query_params
        )
        # If event is scheduled
        if scheduled_event:
            status = self.scheduled(
                isoparse(scheduled_event[0]["start_time"]),
                isoparse(scheduled_event[0]["end_time"])
            )
            await self.update_user_event_message(
                status=status,
                user_event=scheduled_event[0]["user_event"]
            )
            return

        # If event is not scheduled
        await self.update_user_event_message(
            status=NOT_SCHEDULED,
            user_event=user_event
        )

        await ctx.send("Event description updated.")

    @user_event.command(name="delete")
    @is_event_organizer
    async def delete_user_event(self, ctx: Context, event_name: str) -> None:
        """Delete user event."""
        # Check if the event is scheduled
        user_event = await self.bot.api_client.get(f"bot/user-events/{event_name}")

        query_params = {
            "user_event__name": user_event["name"],
            "user_event__organizer": ctx.author.id
        }
        scheduled_event = await self.bot.api_client.get(
            "bot/scheduled-events",
            params=query_params
        )

        # If event is scheduled
        if scheduled_event:
            await ctx.send("Cancel the event before deleting!")
            return

        # Delete user event on site
        await self.bot.api_client.delete(f"bot/user-events/{event_name}")

        # Delete message in #user-events-list channel
        channel = self.user_events_list_channel
        message = await channel.fetch_message(user_event["message_id"])
        await message.delete()

        await ctx.send(f"User Event **{event_name}** deleted!")

    @user_event.command(name="schedule")
    async def schedule_user_event(
            self,
            ctx: Context,
            event_name: str,
            start_datetime: str,
            duration: float = 3.0
    ) -> None:
        """
        Schedule a user event at a particular date and time.

        The time should be in UTC.
        Default duration is 3 hours.

        Examples:
        !userevent schedule minecraft "october 10th 2020 14:00:00" 1.5
        !userevent schedule "among us" "october 10th 2020 14:00:00" 2
        """
        # Check if author is event organizer.
        query_params = {
            "organizer": ctx.author.id
        }
        user_event = await self.bot.api_client.get(
            f"bot/user-events/{event_name}",
            params=query_params,
        )
        # Parse and convert given timestamp to python datetime
        start_datetime = parse(start_datetime)

        if start_datetime < datetime.now():
            await ctx.send("Invalid start datetime.")
            return

        end_datetime = start_datetime + timedelta(hours=duration)

        # Register scheduled event on site
        post_data = {
            "user_event_name": user_event["name"],
            "start_time": start_datetime.isoformat(),
            "end_time": end_datetime.isoformat()
        }
        scheduled_event = await self.bot.api_client.post(
            "bot/scheduled-events",
            data=post_data
        )

        status = self.scheduled(start_datetime, end_datetime)

        # Send message in #user-events-announcements regarding event schedule
        embed = Embed(
            title=f"{user_event['name']} Event Scheduled!",
            description=status
        )

        # Announce scheduled user event
        event_message = await self.user_events_list_channel.fetch_message(scheduled_event["user_event"]["message_id"])
        embed.url = event_message.jump_url + "/discord"
        embed.set_footer(text="Follow embed link and react to message to be notified.")

        await self.user_event_announcement_channel.send(embed=embed)

        # Update status in #user-events-list channel
        await self.update_user_event_message(status, user_event)

        # Set start reminders for scheduled event organizer.
        await self.schedule_event_start_reminder(scheduled_event)

        await ctx.send("Event scheduled.")

    @user_event.command(name="cancel")
    async def cancel_scheduled_event(self, ctx: Context) -> None:
        """Cancel a scheduled event."""
        # Check if user has an event scheduled
        query_params = {
            "user_event__organizer": ctx.author.id
        }
        scheduled_event = await self.bot.api_client.get(
            "bot/scheduled-events",
            params=query_params
        )

        # If user has not scheduled any event
        if not scheduled_event:
            await ctx.send("You do not have an event scheduled.")
            return

        # cancel the scheduler and DELETE on site
        await self._cancel_scheduled_event(scheduled_event[0])

        await ctx.send(f"{scheduled_event[0]['user_event']['name']} event is cancelled.")

    @user_event.command(name="open")
    async def open_voice_channel(self, ctx: Context) -> None:
        """Open the events voice channel for developers."""
        await self.edit_events_vc(open_vc=True)
        await ctx.send("Channel is now open, have fun!")

    @user_event.command(name="announce")
    async def announce_event_start(self, ctx: Context, *, announcement_message: Optional[str]) -> None:
        """Inform all event subscribers that the event is starting."""
        # Get scheduled event
        query_params = {
            "user_event__organizer": ctx.author.id
        }
        # This will error out if event is not scheduled
        scheduled_event = await self.bot.api_client.get(
            "bot/scheduled-events",
            params=query_params
        )
        message_id = scheduled_event[0]["user_event"]["message_id"]

        # Get subscribers
        subscribers = await self.fetch_subscribers(message_id)

        # Remove organizer from subscribers list
        subscribers = [
            sub for sub in subscribers
            if sub.id != scheduled_event[0]["user_event"]["organizer"]
            and not sub.bot
        ]

        # Send message in #user-event-announcements channel
        subscribers = "".join(sub.mention for sub in subscribers)
        message = subscribers

        if announcement_message:
            message += announcement_message

        # Update event status
        status = LIVE
        await self.update_user_event_message(status, scheduled_event[0]["user_event"])

        await self.user_event_announcement_channel.send(message)

    @user_event.command(name="close")
    async def close_voice_channel(self, ctx: Context) -> None:
        """Close the events voice channel for developers."""
        await self.edit_events_vc(open_vc=False)
        await ctx.send("Voice Channel is now closed.")

    async def cog_command_error(self, ctx: Context, error: Exception) -> None:
        """Handle ResponseCodeError locally."""
        # Custom errors are raised via the CommandInvokeError
        if isinstance(error, CommandInvokeError):
            if isinstance(error.original, ResponseCodeError):

                # Parse 400 error responses from site
                if error.original.status == 400:

                    # 400 error messages are usually of the
                    # format -> { field: [error message(s)] }
                    error_message = "\n".join(
                        "\n".join(value)
                        for value in error.original.response_json.values()
                    )

                    await ctx.send(error_message)
                    error.handled = True

    async def cog_check(self, ctx: Context) -> bool:
        """Allow users with event coordinator role to exec cog commands."""
        return (
            await has_role(Roles.user_event_coordinator).predicate(ctx)
            and ctx.channel.id == Channels.user_event_coordinators
        )


def setup(bot: Bot) -> None:
    """Load the UserEvents cog."""
    bot.add_cog(UserEvents(bot))
