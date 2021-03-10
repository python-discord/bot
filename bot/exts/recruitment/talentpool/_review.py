import asyncio
import logging
import textwrap
import typing
from collections import Counter
from datetime import datetime, timedelta
from typing import List, Optional

from dateutil.parser import isoparse
from dateutil.relativedelta import relativedelta
from discord import Member, Message, TextChannel
from discord.ext.commands import Context

from bot.api import ResponseCodeError
from bot.bot import Bot
from bot.constants import Channels, Guild, Roles
from bot.utils.scheduling import Scheduler
from bot.utils.time import get_time_delta, humanize_delta, time_since

if typing.TYPE_CHECKING:
    from bot.exts.recruitment.talentpool._cog import TalentPool

log = logging.getLogger(__name__)

# Maximum amount of days before an automatic review is posted.
MAX_DAYS_IN_POOL = 30

# Maximum amount of characters allowed in a message
MAX_MESSAGE_SIZE = 2000


class Reviewer(Scheduler):
    """Schedules, formats, and publishes reviews of helper nominees."""

    def __init__(self, name: str, bot: Bot, pool: 'TalentPool'):
        super().__init__(name)
        self.bot = bot
        self._pool = pool

    async def reschedule_reviews(self) -> None:
        """Reschedule all active nominations to be reviewed at the appropriate time."""
        log.trace("Rescheduling reviews")
        await self.bot.wait_until_guild_available()
        # TODO Once the watch channel is removed, this can be done in a smarter way, e.g create a sync function.
        await self._pool.fetch_user_cache()

        for user_id, user_data in self._pool.watched_users.items():
            if not user_data["reviewed"]:
                self.schedule_review(user_id)

    def schedule_review(self, user_id: int) -> None:
        """Schedules a single user for review."""
        log.trace(f"Scheduling review of user with ID {user_id}")

        user_data = self._pool.watched_users[user_id]
        inserted_at = isoparse(user_data['inserted_at']).replace(tzinfo=None)
        review_at = inserted_at + timedelta(days=MAX_DAYS_IN_POOL)

        self.schedule_at(review_at, user_id, self.post_review(user_id, update_database=True))

    async def post_review(self, user_id: int, update_database: bool) -> None:
        """Format a generic review of a user and post it to the mod announcements channel."""
        log.trace(f"Posting the review of {user_id}")

        nomination = self._pool.watched_users[user_id]
        guild = self.bot.get_guild(Guild.id)
        channel = guild.get_channel(Channels.mod_announcements)
        member = guild.get_member(user_id)
        if not member:
            channel.send(f"I tried to review the user with ID `{user_id}`, but they don't appear to be on the server 😔")
            return

        if update_database:
            await self.bot.api_client.patch(f"{self._pool.api_endpoint}/{nomination['id']}", json={"reviewed": True})

        opening = f"<@&{Roles.moderators}> <@&{Roles.admins}>\n{member.mention} ({member}) for Helper!"

        current_nominations = "\n\n".join(
            f"**<@{entry['actor']}>:** {entry['reason']}" for entry in nomination['entries']
        )
        current_nominations = f"**Nominated by:**\n{current_nominations}"

        review_body = await self._construct_review_body(member)

        vote_request = "*Refer to their nomination and infraction histories for further details*.\n"
        vote_request += "*Please react 👀 if you've seen this post. Then react 👍 for approval, or 👎 for disapproval*."

        review = "\n\n".join(part for part in (opening, current_nominations, review_body, vote_request))

        message = (await self._bulk_send(channel, review))[-1]
        for reaction in ("👀", "👍", "👎"):
            await message.add_reaction(reaction)

    async def _construct_review_body(self, member: Member) -> str:
        """Formats the body of the nomination, with details of activity, infractions, and previous nominations."""
        activity = await self._activity_review(member)
        infractions = await self._infractions_review(member)
        prev_nominations = await self._previous_nominations_review(member)

        body = f"{activity}\n\n{infractions}"
        if prev_nominations:
            body += f"\n\n{prev_nominations}"
        return body

    async def _activity_review(self, member: Member) -> str:
        """
        Format the activity of the nominee.

        Adds details on how long they've been on the server, their total message count,
        and the channels they're the most active in.
        """
        log.trace(f"Fetching the metricity data for {member.id}'s review")
        try:
            user_activity = await self.bot.api_client.get(f"bot/users/{member.id}/metricity_review_data")
        except ResponseCodeError as e:
            if e.status == 404:
                messages = "no"
                channels = ""
            else:
                raise
        else:
            messages = user_activity["total_messages"]
            # Making this part flexible to the amount of expected and returned channels.
            first_channel = user_activity["top_channel_activity"][0]
            channels = f", with {first_channel[1]} messages in {first_channel[0]}"

            if len(user_activity["top_channel_activity"]) > 1:
                channels += ", " + ", ".join(
                    f"{count} in {channel}" for channel, count in user_activity["top_channel_activity"][1: -1]
                )
                last_channel = user_activity["top_channel_activity"][-1]
                channels += f", and {last_channel[1]} in {last_channel[0]}"

        time_on_server = humanize_delta(relativedelta(datetime.utcnow(), member.joined_at), max_units=2)
        review = f"{member.name} has been on the server for **{time_on_server}**"
        review += f" and has **{messages} messages**{channels}."

        return review

    async def _infractions_review(self, member: Member) -> str:
        """
        Formats the review of the nominee's infractions, if any.

        The infractions are listed by type and amount, and it is stated how long ago the last one was issued.
        """
        log.trace(f"Fetching the infraction data for {member.id}'s review")
        infraction_list = await self.bot.api_client.get(
            'bot/infractions/expanded',
            params={'user__id': str(member.id), 'ordering': '-inserted_at'}
        )

        if not infraction_list:
            return "They have no infractions."

        # Count the amount of each type of infraction.
        infr_stats = list(Counter(infr["type"] for infr in infraction_list).items())

        # Format into a sentence.
        infractions = ", ".join(
            f"{count} {self._format_infr_name(infr_type, count)}"
            for infr_type, count in infr_stats[:-1]
        )
        if len(infr_stats) > 1:
            last_infr, last_count = infr_stats[-1]
            infractions += f", and {last_count} {self._format_infr_name(last_infr, last_count)}"

        infractions = f"**{infractions}**"

        # Show when the last one was issued.
        if len(infraction_list) == 1:
            infractions += ", issued "
        else:
            infractions += ", with the last infraction issued "

        # Infractions were ordered by time since insertion descending.
        infractions += get_time_delta(infraction_list[0]['inserted_at'])

        return f"They have {infractions}."

    @staticmethod
    def _format_infr_name(infr_type: str, count: int) -> str:
        """
        Format the infraction type in a way readable in a sentence.

        Underscores are replaced with spaces, as well as *attempting* to show the appropriate plural form if necessary.
        This function by no means covers all rules of grammar.
        """
        formatted = infr_type.replace("_", " ")
        if count > 1:
            if infr_type.endswith(('ch', 'sh')):
                formatted += "e"
            formatted += "s"

        return formatted

    async def _previous_nominations_review(self, member: Member) -> Optional[str]:
        """
        Formats the review of the nominee's previous nominations.

        The number of previous nominations and unnominations are shown, as well as the reason the last one ended.
        """
        log.trace(f"Fetching the nomination history data for {member.id}'s review")
        history = await self.bot.api_client.get(
            self._pool.api_endpoint,
            params={
                "user__id": str(member.id),
                "active": "false",
                "ordering": "-inserted_at"
            }
        )

        if not history:
            return

        num_entries = sum(len(nomination["entries"]) for nomination in history)

        nomination_times = f"{num_entries} times" if num_entries > 1 else "once"
        rejection_times = f"{len(history)} times" if len(history) > 1 else "once"
        review = f"They were nominated **{nomination_times}** before"
        review += f", but their nomination was called off **{rejection_times}**."

        end_time = time_since(isoparse(history[0]['ended_at']).replace(tzinfo=None), max_units=2)
        review += f"\nThe last one ended {end_time} with the reason: {history[0]['end_reason']}"

        return review

    @staticmethod
    async def _bulk_send(channel: TextChannel, text: str) -> List[Message]:
        """
        Split a text into several if necessary, and post them to the channel.

        Returns the resulting message objects.
        """
        messages = textwrap.wrap(text, width=MAX_MESSAGE_SIZE, replace_whitespace=False)

        results = []
        for message in messages:
            await asyncio.sleep(1)
            results.append(await channel.send(message))

        return results

    async def mark_reviewed(self, ctx: Context, nomination_id: int) -> Optional[int]:
        """
        Mark an active nomination as reviewed, updating the database and canceling the review task.

        On success, returns the user ID.
        """
        log.trace(f"Updating nomination #{nomination_id} as review")
        try:
            nomination = await self.bot.api_client.get(f"{self._pool.api_endpoint}/{nomination_id}")
        except ResponseCodeError as e:
            if e.response.status == 404:
                self.log.trace(f"Nomination API 404: Can't find nomination with id {nomination_id}")
                await ctx.send(f"❌ Can't find a nomination with id `{nomination_id}`")
                return None
            else:
                raise

        if nomination["reviewed"]:
            await ctx.send("❌ This nomination was already reviewed, but here's a cookie 🍪")
            return None
        elif not nomination["active"]:
            await ctx.send("❌ This nomination is inactive")
            return None

        await self.bot.api_client.patch(f"{self._pool.api_endpoint}/{nomination['id']}", json={"reviewed": True})
        if nomination["user"] in self:
            self.cancel(nomination["user"])

        await self._pool.fetch_user_cache()

        return nomination["user"]
