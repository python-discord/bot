import contextlib
import random
import re
import typing
from collections import Counter
from datetime import UTC, datetime, timedelta

import discord
from async_rediscache import RedisCache
from discord import Embed, Emoji, Member, NotFound, PartialMessage
from pydis_core.site_api import ResponseCodeError
from pydis_core.utils.channel import get_or_fetch_channel
from pydis_core.utils.members import get_or_fetch_member

from bot.bot import Bot
from bot.constants import Channels, Colours, Emojis, Guild, Roles
from bot.exts.recruitment.talentpool._api import Nomination, NominationAPI, NominationEntry
from bot.log import get_logger
from bot.utils import time
from bot.utils.messages import count_unique_users_reaction

if typing.TYPE_CHECKING:
    from bot.exts.utils.thread_bumper import ThreadBumper

log = get_logger(__name__)

# Maximum amount of characters allowed in a message
MAX_MESSAGE_SIZE = 2000
# Maximum amount of characters allowed in an embed
MAX_EMBED_SIZE = 4000

# Maximum number of active reviews
MAX_ONGOING_REVIEWS = 3
# Maximum number of total reviews
MAX_TOTAL_REVIEWS = 10
# Minimum time between reviews
MIN_REVIEW_INTERVAL = timedelta(days=1)
# Minimum time between nomination and sending a review
MIN_NOMINATION_TIME = timedelta(days=7)
# Number of days ago that the user must have activity since
RECENT_ACTIVITY_DAYS = 7

# A constant for weighting number of nomination entries against nomination age when selecting a user to review.
# The higher this is, the lower the effect of review age. At 1, age and number of entries are weighted equally.
REVIEW_SCORE_WEIGHT = 1.5

# Regex for finding a nomination, and extracting the nominee.
NOMINATION_MESSAGE_REGEX = re.compile(
    r"<@!?(\d+)> \(.+(#\d{4})?\) for Helper!\n\n",
    re.MULTILINE
)


class Reviewer:
    """Manages, formats, and publishes reviews of helper nominees."""

    # RedisCache[
    #    "last_vote_date": float   | POSIX UTC timestamp.
    # ]
    status_cache = RedisCache()

    def __init__(self, bot: Bot, nomination_api: NominationAPI):
        self.bot = bot
        self.api = nomination_api

    async def maybe_review_user(self) -> bool:
        """
        Checks if a new vote should be triggered, and triggers one if ready.

        Returns a boolean representing whether a new vote was sent or not.
        """
        if not await self.is_ready_for_review():
            return False

        nomination = await self.get_nomination_to_review()
        if not nomination:
            return False

        await self.post_review(nomination)
        return True

    async def is_ready_for_review(self) -> bool:
        """
        Returns a boolean representing whether a new vote should be triggered.

        The criteria for this are:
         - The current number of reviews is lower than `MAX_ONGOING_REVIEWS`.
         - The most recent review was sent less than `MIN_REVIEW_INTERVAL` ago.
        """
        voting_channel = self.bot.get_channel(Channels.nomination_voting)

        last_vote_timestamp = await self.status_cache.get("last_vote_date")
        if last_vote_timestamp:
            last_vote_date = datetime.fromtimestamp(last_vote_timestamp, tz=UTC)
            time_since_last_vote = datetime.now(UTC) - last_vote_date

            if time_since_last_vote < MIN_REVIEW_INTERVAL:
                log.debug("Most recent review was less than %s ago, cancelling check", MIN_REVIEW_INTERVAL)
                return False
        else:
            log.info("Date of last vote not found in cache, a vote may be sent early")

        ongoing_count = 0
        total_count = 0

        async for msg in voting_channel.history():
            # Try and filter out any non-review messages. We also only want to count
            # one message from reviews split over multiple messages. We use fixed text
            # from the start as any later text could be split over messages.
            if not msg.author.bot or "for Helper!" not in msg.content:
                continue

            total_count += 1

            is_ticketed = False
            for reaction in msg.reactions:
                if reaction.emoji == "\N{TICKET}":
                    is_ticketed = True

            if not is_ticketed:
                ongoing_count += 1

            if ongoing_count >= MAX_ONGOING_REVIEWS or total_count >= MAX_TOTAL_REVIEWS:
                log.debug(
                    "There are %s ongoing and %s total reviews, above thresholds of %s and %s",
                    ongoing_count, total_count,
                    MAX_ONGOING_REVIEWS, MAX_TOTAL_REVIEWS
                )
                return False

        return True

    @staticmethod
    def is_nomination_old_enough(nomination: Nomination, now: datetime) -> bool:
        """Check if a nomination is old enough to autoreview."""
        time_since_nomination = now - nomination.inserted_at
        return time_since_nomination > MIN_NOMINATION_TIME

    @staticmethod
    def is_user_active_enough(user_message_count: int) -> bool:
        """Check if a user's message count is enough for them to be autoreviewed."""
        return user_message_count > 0

    async def is_nomination_ready_for_review(
        self,
        nomination: Nomination,
        user_message_count: int,
        now: datetime,
    ) -> bool:
        """
        Returns a boolean representing whether a nomination should be reviewed.

        Users will only be selected for review if:
         - They have not already been reviewed.
         - They have been nominated for longer than `MIN_NOMINATION_TIME`.
         - They have sent at least one message in the server recently.
         - They are still a member of the server.
        """
        guild = self.bot.get_guild(Guild.id)
        return (
            # Must be an active nomination
            nomination.active and
            # ... that has not already been reviewed
            not nomination.reviewed and
            # ... and has been nominated for long enough
            self.is_nomination_old_enough(nomination, now) and
            # ... and is for a user that has been active recently
            self.is_user_active_enough(user_message_count) and
            # ... and is currently a member of the server
            await get_or_fetch_member(guild, nomination.user_id) is not None
        )

    async def sort_nominations_to_review(self, nominations: list[Nomination], now: datetime) -> list[Nomination]:
        """
        Sorts a list of nominations by priority for review.

        The priority of the review is determined based on how many nominations the user has
        (more nominations = higher priority), and the age of the nomination.
        """
        if not nominations:
            return []

        oldest_date = min(nomination.inserted_at for nomination in nominations)
        max_entries = max(len(nomination.entries) for nomination in nominations)

        def score_nomination(nomination: Nomination) -> float:
            """
            Scores a nomination based on age and number of nomination entries.

            The higher the score, the higher the priority for being put up for review should be.
            """
            num_entries = len(nomination.entries)
            entries_score = num_entries / max_entries

            nomination_date = nomination.inserted_at
            age_score = (nomination_date - now) / (oldest_date - now)

            return entries_score * REVIEW_SCORE_WEIGHT + age_score

        return sorted(nominations, key=score_nomination, reverse=True)

    async def get_nomination_to_review(self) -> Nomination | None:
        """
        Returns the Nomination of the next user to review, or None if there are no users ready.

        See `is_ready_for_review` for the criteria for a user to be ready for review.
        See `sort_nominations_to_review` for the criteria for a user to be prioritised for review.
        """
        now = datetime.now(UTC)
        nominations = await self.api.get_nominations(active=True)
        if not nominations:
            return None

        messages_per_user = await self.api.get_activity(
            [nomination.user_id for nomination in nominations],
            days=RECENT_ACTIVITY_DAYS,
        )
        possible_nominations = [
            nomination for nomination in nominations
            if await self.is_nomination_ready_for_review(nomination, messages_per_user[nomination.user_id], now)
        ]
        if not possible_nominations:
            log.info("No nominations are ready to review")
            return None

        sorted_nominations = await self.sort_nominations_to_review(possible_nominations, now)
        return sorted_nominations[0]

    async def post_review(self, nomination: Nomination) -> None:
        """Format the review of a user and post it to the nomination voting channel."""
        review, reviewed_emoji, nominee, nominations = await self.make_review(nomination)
        if not nominee:
            return

        guild = self.bot.get_guild(Guild.id)
        channel = guild.get_channel(Channels.nomination_voting)

        log.info(f"Posting the review of {nominee} ({nominee.id})")
        vote_message = await channel.send(review)

        if reviewed_emoji:
            for reaction in (reviewed_emoji, "\N{THUMBS UP SIGN}", "\N{THUMBS DOWN SIGN}"):
                await vote_message.add_reaction(reaction)

        thread = await vote_message.create_thread(
            name=f"Nomination - {nominee}",
        )

        nomination_messages = []
        for batch in nominations:
            nomination_messages.append(await thread.send(batch))

        # Pin the later messages first so the "Nominated by:" message is at the top of the pins list
        for nom_message in nomination_messages[::-1]:
            await nom_message.pin()

        message = await thread.send(f"<@&{Roles.mod_team}> <@&{Roles.admins}>")

        now = datetime.now(tz=UTC)
        await self.status_cache.set("last_vote_date", now.timestamp())

        await self.api.edit_nomination(nomination.id, reviewed=True, thread_id=thread.id)

        bump_cog: ThreadBumper = self.bot.get_cog("ThreadBumper")
        if bump_cog:
            context = await self.bot.get_context(message)
            await bump_cog.add_thread_to_bump_list(context, thread)

    async def make_review(self, nomination: Nomination) -> tuple[str, Emoji | None, Member | None]:
        """Format a generic review of a user and return it with the reviewed emoji and the user themselves."""
        log.trace(f"Formatting the review of {nomination.user_id}")

        guild = self.bot.get_guild(Guild.id)
        nominee = await get_or_fetch_member(guild, nomination.user_id)

        if not nominee:
            return (
                f"I tried to review the user with ID `{nomination.user_id}`,"
                " but they don't appear to be on the server :pensive:"
            ), None, None

        opening = f"{nominee.mention} ({nominee}) for Helper!"

        nominations = self._make_nomination_batches(nomination.entries)

        review_body = await self._construct_review_body(nominee, nomination)

        reviewed_emoji = self._random_ducky(guild)
        vote_request = (
            "*Refer to their nomination and infraction histories for further details.*\n"
            f"*Please react {reviewed_emoji} once you have reviewed this user,"
            " and react :+1: for approval, or :-1: for disapproval*."
        )

        review = "\n\n".join((opening, review_body, vote_request))
        return review, reviewed_emoji, nominee, nominations

    def _make_nomination_batches(self, entries: list[NominationEntry]) -> list[str]:
        """Construct the batches of nominations to send into the voting thread."""
        messages = ["**Nominated by:**"]

        formatted = [f"**<@{entry.actor_id}>:** {entry.reason or '*no reason given*'}" for entry in entries[::-1]]

        for entry in formatted:
            # Add the nomination to the current last message in the message batches
            potential_message = messages[-1] + f"\n\n{entry}"

            # Test if adding this entry pushes us over the character limit
            if len(potential_message) >= MAX_MESSAGE_SIZE:
                # If it does, create a new message starting with this entry
                messages.append(entry)
            else:
                # If it doesn't, we will use this message
                messages[-1] = potential_message

        return messages

    async def archive_vote(self, message: PartialMessage, passed: bool) -> None:
        """Archive this vote to #nomination-archive."""
        message = await message.fetch()

        # Thread channel IDs are the same as the message ID of the parent message.
        nomination_thread = message.guild.get_thread(message.id)
        if not nomination_thread:
            try:
                nomination_thread = await message.guild.fetch_channel(message.id)
            except NotFound:
                log.warning(f"Could not find a thread linked to {message.channel.id}-{message.id}")

        # We assume that the first user mentioned is the user that we are voting on
        user_id = int(NOMINATION_MESSAGE_REGEX.search(message.content).group(1))

        # Get reaction counts
        reviewed = await count_unique_users_reaction(
            message,
            lambda r: "ducky" in str(r) or str(r) == "\N{EYES}",
            count_bots=False
        )
        upvotes = await count_unique_users_reaction(
            message,
            lambda r: str(r) == "\N{THUMBS UP SIGN}",
            count_bots=False
        )
        downvotes = await count_unique_users_reaction(
            message,
            lambda r: str(r) == "\N{THUMBS DOWN SIGN}",
            count_bots=False
        )

        # Remove the first and last paragraphs
        stripped_content = message.content.split("\n\n", maxsplit=1)[1].rsplit("\n\n", maxsplit=1)[0]

        result = f"**Passed** {Emojis.incident_actioned}" if passed else f"**Rejected** {Emojis.incident_unactioned}"
        colour = Colours.soft_green if passed else Colours.soft_red
        timestamp = datetime.now(tz=UTC).strftime("%Y/%m/%d")

        if nomination_thread:
            thread_jump = f"[Jump to vote thread]({nomination_thread.jump_url})"
        else:
            thread_jump = "Failed to get thread"

        embed_content = (
            f"{result} on {timestamp}\n"
            f"With {reviewed} {Emojis.ducky_dave} {upvotes} :+1: {downvotes} :-1:\n"
            f"{thread_jump}\n\n"
            f"{stripped_content}"
        )

        if user := await self.bot.fetch_user(user_id):
            embed_title = f"Vote for {user} (`{user.id}`)"
        else:
            embed_title = f"Vote for `{user_id}`"

        channel = self.bot.get_channel(Channels.nomination_voting_archive)
        await channel.send(embed=Embed(
            title=embed_title,
            description=embed_content,
            colour=colour
        ))

        await message.delete()

        if nomination_thread:
            with contextlib.suppress(NotFound):
                await nomination_thread.edit(archived=True)

    async def _construct_review_body(self, member: Member, nomination: Nomination) -> str:
        """Formats the body of the nomination, with details of activity, infractions, and previous nominations."""
        activity = await self._activity_review(member)
        nominations = await self._nominations_review(nomination)
        infractions = await self._infractions_review(member)
        prev_nominations = await self._previous_nominations_review(member)

        body = f"{nominations}\n\n{activity}\n\n{infractions}"
        if prev_nominations:
            body += f"\n\n{prev_nominations}"
        return body

    async def _nominations_review(self, nomination: Nomination) -> str:
        """Format a brief summary of how many nominations in this voting round the nominee has."""
        entry_count = len(nomination.entries)

        return f"They have **{entry_count}** nomination{'s' if entry_count != 1 else ''} this round."

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
                log.trace(f"The user {member.id} seems to have no activity logged in Metricity.")
                messages = "no"
                channels = ""
            else:
                log.trace(f"An unexpected error occured while fetching information of user {member.id}.")
                raise
        else:
            log.trace(f"Activity found for {member.id}, formatting review.")
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

        joined_at_formatted = time.format_relative(member.joined_at)
        review = (
            f"{member.name} joined the server **{joined_at_formatted}**"
            f" and has **{messages} messages**{channels}."
        )

        return review

    async def _infractions_review(self, member: Member) -> str:
        """
        Formats the review of the nominee's infractions, if any.

        The infractions are listed by type and amount, and it is stated how long ago the last one was issued.
        """
        log.trace(f"Fetching the infraction data for {member.id}'s review")
        infraction_list = await self.bot.api_client.get(
            "bot/infractions/expanded",
            params={"user__id": str(member.id), "ordering": "-inserted_at"}
        )

        log.trace(f"{len(infraction_list)} infractions found for {member.id}, formatting review.")
        if not infraction_list:
            return "They have no infractions."

        # Count the amount of each type of infraction.
        infr_stats = list(Counter(infr["type"] for infr in infraction_list).items())

        # Format into a sentence.
        if len(infr_stats) == 1:
            infr_type, count = infr_stats[0]
            infractions = f"{count} {self._format_infr_name(infr_type, count)}"
        else:  # We already made sure they have infractions.
            infractions = ", ".join(
                f"{count} {self._format_infr_name(infr_type, count)}"
                for infr_type, count in infr_stats[:-1]
            )
            last_infr, last_count = infr_stats[-1]
            infractions += f", and {last_count} {self._format_infr_name(last_infr, last_count)}"

        infractions = f"**{infractions}**"

        # Show when the last one was issued.
        if len(infraction_list) == 1:
            infractions += ", issued "
        else:
            infractions += ", with the last infraction issued "

        # Infractions were ordered by time since insertion descending.
        infractions += time.format_relative(infraction_list[0]["inserted_at"])

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
            if infr_type.endswith(("ch", "sh")):
                formatted += "e"
            formatted += "s"

        return formatted

    async def _previous_nominations_review(self, member: Member) -> str | None:
        """
        Formats the review of the nominee's previous nominations.

        The number of previous nominations and unnominations are shown, as well as the reason the last one ended.
        """
        log.trace(f"Fetching the nomination history data for {member.id}'s review")
        history = await self.api.get_nominations(user_id=member.id, active=False)

        log.trace(f"{len(history)} previous nominations found for {member.id}, formatting review.")
        if not history:
            return None

        num_entries = sum(len(nomination.entries) for nomination in history)

        nomination_times = f"{num_entries} times" if num_entries > 1 else "once"
        rejection_times = f"{len(history)} times" if len(history) > 1 else "once"
        thread_jump_urls = []

        for nomination in history:
            if nomination.thread_id is None:
                continue
            try:
                thread = await get_or_fetch_channel(self.bot, nomination.thread_id)
            except discord.HTTPException:
                # Nothing to do here
                pass
            else:
                thread_jump_urls.append(thread.jump_url)

        if not thread_jump_urls:
            nomination_vote_threads = "No nomination threads have been found for this user."
        else:
            nomination_vote_threads = ", ".join(thread_jump_urls)

        end_time = time.format_relative(history[0].ended_at)

        review = (
            f"They were nominated **{nomination_times}** before"
            f", but their nomination was called off **{rejection_times}**."
            f"\nList of all of their nomination threads: {nomination_vote_threads}"
            f"\nThe last one ended {end_time} with the reason: {history[0].end_reason}"
        )

        return review

    @staticmethod
    def _random_ducky(guild: Guild) -> Emoji | str:
        """Picks a random ducky emoji. If no duckies found returns 👀."""
        duckies = [emoji for emoji in guild.emojis if emoji.name.startswith("ducky")]
        if not duckies:
            return "\N{EYES}"
        return random.choice(duckies)
