import asyncio
import contextlib
import random
import re
import textwrap
import typing
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Union

from botcore.site_api import ResponseCodeError
from dateutil.parser import isoparse
from discord import Embed, Emoji, Member, Message, NotFound, PartialMessage, TextChannel
from discord.ext.commands import Context

from bot.bot import Bot
from bot.constants import Channels, Colours, Emojis, Guild, Roles
from bot.log import get_logger
from bot.utils import time
from bot.utils.members import get_or_fetch_member
from bot.utils.messages import count_unique_users_reaction, pin_no_system_message

if typing.TYPE_CHECKING:
    from bot.exts.recruitment.talentpool._cog import TalentPool
    from bot.exts.utils.thread_bumper import ThreadBumper

log = get_logger(__name__)

# Maximum amount of characters allowed in a message
MAX_MESSAGE_SIZE = 2000
# Maximum amount of characters allowed in an embed
MAX_EMBED_SIZE = 4000

# Maximum number of active reviews
MAX_ONGOING_REVIEWS = 4
# Minimum time between reviews
MIN_REVIEW_INTERVAL = timedelta(days=1)
# Minimum time between nomination and sending a review
MIN_NOMINATION_TIME = timedelta(days=7)

# Regex for finding the first message of a nomination, and extracting the nominee.
NOMINATION_MESSAGE_REGEX = re.compile(
    r"<@!?(\d+)> \(.+#\d{4}\) for Helper!\n\n",
    re.MULTILINE
)

# This is a constant so we can detect the final message in a nomination. Keep this in mind
# if changing this value.
REVIEW_FOOTER_MESSAGE = "*Refer to their nomination and infraction histories for further details.*"


class Reviewer:
    """Manages, formats, and publishes reviews of helper nominees."""

    def __init__(self, name: str, bot: Bot, pool: 'TalentPool'):
        self.bot = bot
        self._pool = pool

    async def maybe_review_user(self) -> bool:
        """
        Checks if a new vote should be triggered, and triggers one if ready.

        Returns a boolean representing whether a new vote was sent or not.
        """
        if not await self.is_ready_for_review():
            return False

        user = await self.get_user_for_review()
        if not user:
            return False

        await self.post_review(user, True)
        return True

    async def is_ready_for_review(self) -> bool:
        """
        Returns a boolean representing whether a new vote should be triggered.

        The criteria for this are:
         - The current number of reviews is lower than `MAX_ONGOING_REVIEWS`.
         - The most recent review was sent less than `MIN_REVIEW_INTERVAL` ago.
        """
        voting_channel = self.bot.get_channel(Channels.nomination_voting)

        review_count = 0
        is_first_message = True
        async for msg in voting_channel.history():
            # Try and filter out any non-review messages. We also only want to count
            # the final message in the case of reviews split over multiple messages.
            if not msg.author.bot or REVIEW_FOOTER_MESSAGE not in msg.content:
                continue

            if is_first_message:
                if msg.created_at > datetime.now(timezone.utc) - MIN_REVIEW_INTERVAL:
                    log.debug("Most recent review was less than %s ago, cancelling check", MIN_REVIEW_INTERVAL)
                    return False

                is_first_message = False

            review_count += 1

            if review_count >= MAX_ONGOING_REVIEWS:
                log.debug("There are already at least %s ongoing reviews, cancelling check.", MAX_ONGOING_REVIEWS)
                return False

        return True

    async def get_user_for_review(self) -> Optional[int]:
        """
        Returns the user ID of the next user to review, or None if there are no users ready.

        Users will only be selected for review if:
         - They have not already been reviewed.
         - They have been nominated for longer than `MIN_NOMINATION_TIME`.

        The priority of the review is determined by how many nominations the user has
        (more nominations = higher priority).
        For users with equal priority the oldest nomination will be reviewed first.
        """
        possible = []
        for user_id, user_data in self._pool.cache.items():
            if (
                not user_data["reviewed"]
                and isoparse(user_data["inserted_at"]) < datetime.now(timezone.utc) - MIN_NOMINATION_TIME
            ):
                possible.append((user_id, user_data))

        if not possible:
            log.debug("No users ready to review.")
            return None

        # Secondary sort key: creation of first entries on the nomination.
        possible.sort(key=lambda x: isoparse(x[1]["inserted_at"]))

        # Primary sort key: number of entries on the nomination.
        user = max(possible, key=lambda x: len(x[1]["entries"]))

        return user[0]  # user id

    async def post_review(self, user_id: int, update_database: bool) -> None:
        """Format the review of a user and post it to the nomination voting channel."""
        review, reviewed_emoji, nominee = await self.make_review(user_id)
        if not nominee:
            return

        guild = self.bot.get_guild(Guild.id)
        channel = guild.get_channel(Channels.nomination_voting)

        log.info(f"Posting the review of {nominee} ({nominee.id})")
        messages = await self._bulk_send(channel, review)

        await pin_no_system_message(messages[0])

        last_message = messages[-1]
        if reviewed_emoji:
            for reaction in (reviewed_emoji, "\N{THUMBS UP SIGN}", "\N{THUMBS DOWN SIGN}"):
                await last_message.add_reaction(reaction)

        thread = await last_message.create_thread(
            name=f"Nomination - {nominee}",
        )
        message = await thread.send(f"<@&{Roles.mod_team}> <@&{Roles.admins}>")

        if update_database:
            nomination = self._pool.cache.get(user_id)
            await self.bot.api_client.patch(f"bot/nominations/{nomination['id']}", json={"reviewed": True})

        bump_cog: ThreadBumper = self.bot.get_cog("ThreadBumper")
        if bump_cog:
            context = await self.bot.get_context(message)
            await bump_cog.add_thread_to_bump_list(context, thread)

    async def make_review(self, user_id: int) -> typing.Tuple[str, Optional[Emoji], Optional[Member]]:
        """Format a generic review of a user and return it with the reviewed emoji and the user themselves."""
        log.trace(f"Formatting the review of {user_id}")

        # Since `cache` is a defaultdict, we should take care
        # not to accidentally insert the IDs of users that have no
        # active nominated by using the `cache.get(user_id)`
        # instead of `cache[user_id]`.
        nomination = self._pool.cache.get(user_id)
        if not nomination:
            log.trace(f"There doesn't appear to be an active nomination for {user_id}")
            return f"There doesn't appear to be an active nomination for {user_id}", None, None

        guild = self.bot.get_guild(Guild.id)
        nominee = await get_or_fetch_member(guild, user_id)

        if not nominee:
            return (
                f"I tried to review the user with ID `{user_id}`, but they don't appear to be on the server :pensive:"
            ), None, None

        opening = f"{nominee.mention} ({nominee}) for Helper!"

        current_nominations = "\n\n".join(
            f"**<@{entry['actor']}>:** {entry['reason'] or '*no reason given*'}"
            for entry in nomination['entries'][::-1]
        )
        current_nominations = f"**Nominated by:**\n{current_nominations}"

        review_body = await self._construct_review_body(nominee)

        reviewed_emoji = self._random_ducky(guild)
        vote_request = (
            f"{REVIEW_FOOTER_MESSAGE}.\n"
            f"*Please react {reviewed_emoji} once you have reviewed this user,"
            " and react :+1: for approval, or :-1: for disapproval*."
        )

        review = "\n\n".join((opening, current_nominations, review_body, vote_request))
        return review, reviewed_emoji, nominee

    async def archive_vote(self, message: PartialMessage, passed: bool) -> None:
        """Archive this vote to #nomination-archive."""
        message = await message.fetch()

        # We consider the first message in the nomination to contain the user ping, username#discrim, and fixed text
        messages = [message]
        if not NOMINATION_MESSAGE_REGEX.search(message.content):
            async for new_message in message.channel.history(before=message.created_at):
                messages.append(new_message)

                if NOMINATION_MESSAGE_REGEX.search(new_message.content):
                    break

        log.debug(f"Found {len(messages)} messages: {', '.join(str(m.id) for m in messages)}")

        parts = []
        for message_ in messages[::-1]:
            parts.append(message_.content)
            parts.append("\n" if message_.content.endswith(".") else " ")
        content = "".join(parts)

        # We assume that the first user mentioned is the user that we are voting on
        user_id = int(NOMINATION_MESSAGE_REGEX.search(content).group(1))

        # Get reaction counts
        reviewed = await count_unique_users_reaction(
            messages[0],
            lambda r: "ducky" in str(r) or str(r) == "\N{EYES}",
            count_bots=False
        )
        upvotes = await count_unique_users_reaction(
            messages[0],
            lambda r: str(r) == "\N{THUMBS UP SIGN}",
            count_bots=False
        )
        downvotes = await count_unique_users_reaction(
            messages[0],
            lambda r: str(r) == "\N{THUMBS DOWN SIGN}",
            count_bots=False
        )

        # Remove the first and last paragraphs
        stripped_content = content.split("\n\n", maxsplit=1)[1].rsplit("\n\n", maxsplit=1)[0]

        result = f"**Passed** {Emojis.incident_actioned}" if passed else f"**Rejected** {Emojis.incident_unactioned}"
        colour = Colours.soft_green if passed else Colours.soft_red
        timestamp = datetime.utcnow().strftime("%Y/%m/%d")

        embed_content = (
            f"{result} on {timestamp}\n"
            f"With {reviewed} {Emojis.ducky_dave} {upvotes} :+1: {downvotes} :-1:\n\n"
            f"{stripped_content}"
        )

        if user := await self.bot.fetch_user(user_id):
            embed_title = f"Vote for {user} (`{user.id}`)"
        else:
            embed_title = f"Vote for `{user_id}`"

        channel = self.bot.get_channel(Channels.nomination_archive)
        for number, part in enumerate(
                textwrap.wrap(embed_content, width=MAX_EMBED_SIZE, replace_whitespace=False, placeholder="")
        ):
            await channel.send(embed=Embed(
                title=embed_title if number == 0 else None,
                description="[...] " + part if number != 0 else part,
                colour=colour
            ))

        # Thread channel IDs are the same as the message ID of the parent message.
        nomination_thread = message.guild.get_thread(message.id)
        if not nomination_thread:
            try:
                nomination_thread = await message.guild.fetch_channel(message.id)
            except NotFound:
                log.warning(f"Could not find a thread linked to {message.channel.id}-{message.id}")
                return

        for message_ in messages:
            with contextlib.suppress(NotFound):
                await message_.delete()

        with contextlib.suppress(NotFound):
            await nomination_thread.edit(archived=True)

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
            'bot/infractions/expanded',
            params={'user__id': str(member.id), 'ordering': '-inserted_at'}
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
        infractions += time.format_relative(infraction_list[0]['inserted_at'])

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
            "bot/nominations",
            params={
                "user__id": str(member.id),
                "active": "false",
                "ordering": "-inserted_at"
            }
        )

        log.trace(f"{len(history)} previous nominations found for {member.id}, formatting review.")
        if not history:
            return

        num_entries = sum(len(nomination["entries"]) for nomination in history)

        nomination_times = f"{num_entries} times" if num_entries > 1 else "once"
        rejection_times = f"{len(history)} times" if len(history) > 1 else "once"
        end_time = time.format_relative(history[0]['ended_at'])

        review = (
            f"They were nominated **{nomination_times}** before"
            f", but their nomination was called off **{rejection_times}**."
            f"\nThe last one ended {end_time} with the reason: {history[0]['end_reason']}"
        )

        return review

    @staticmethod
    def _random_ducky(guild: Guild) -> Union[Emoji, str]:
        """Picks a random ducky emoji. If no duckies found returns 👀."""
        duckies = [emoji for emoji in guild.emojis if emoji.name.startswith("ducky")]
        if not duckies:
            return "\N{EYES}"
        return random.choice(duckies)

    @staticmethod
    async def _bulk_send(channel: TextChannel, text: str) -> List[Message]:
        """
        Split a text into several if necessary, and post them to the channel.

        Returns the resulting message objects.
        """
        messages = textwrap.wrap(text, width=MAX_MESSAGE_SIZE, replace_whitespace=False)
        log.trace(f"The provided string will be sent to the channel {channel.id} as {len(messages)} messages.")

        results = []
        for message in messages:
            await asyncio.sleep(1)
            results.append(await channel.send(message))

        return results

    async def mark_reviewed(self, ctx: Context, user_id: int) -> bool:
        """
        Mark an active nomination as reviewed, updating the database and canceling the review task.

        Returns True if the user was successfully marked as reviewed, False otherwise.
        """
        log.trace(f"Updating user {user_id} as reviewed")
        await self._pool.refresh_cache()
        if user_id not in self._pool.cache:
            log.trace(f"Can't find a nominated user with id {user_id}")
            await ctx.send(f":x: Can't find a currently nominated user with id `{user_id}`")
            return False

        nomination = self._pool.cache.get(user_id)
        if nomination["reviewed"]:
            await ctx.send(":x: This nomination was already reviewed, but here's a cookie :cookie:")
            return False

        await self.bot.api_client.patch(f"bot/nominations/{nomination['id']}", json={"reviewed": True})

        return True
