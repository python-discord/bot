import logging
import random
import re
from typing import Optional

from discord import Colour, Embed, Message, TextChannel, User
from discord.ext.commands import Cog, Context, group

from bot.bot import Bot
from bot.cogs.moderation import ModLog
from bot.constants import (
    Channels, CleanMessages, Colours, Event,
    Icons, MODERATION_ROLES, NEGATIVE_REPLIES
)
from bot.decorators import with_role

log = logging.getLogger(__name__)


class Clean(Cog):
    """
    A cog that allows messages to be deleted in bulk, while applying various filters.

    You can delete messages sent by a specific user, messages sent by bots, all messages, or messages that match a
    specific regular expression.

    The deleted messages are saved and uploaded to the database via an API endpoint, and a URL is returned which can be
    used to view the messages in the Discord dark theme style.
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self.cleaning = False

    @property
    def mod_log(self) -> ModLog:
        """Get currently loaded ModLog cog instance."""
        return self.bot.get_cog("ModLog")

    async def _clean_messages(
        self,
        amount: int,
        ctx: Context,
        bots_only: bool = False,
        user: User = None,
        regex: Optional[str] = None,
        channel: Optional[TextChannel] = None
    ) -> None:
        """A helper function that does the actual message cleaning."""
        def predicate_bots_only(message: Message) -> bool:
            """Return True if the message was sent by a bot."""
            return message.author.bot

        def predicate_specific_user(message: Message) -> bool:
            """Return True if the message was sent by the user provided in the _clean_messages call."""
            return message.author == user

        def predicate_regex(message: Message) -> bool:
            """Check if the regex provided in _clean_messages matches the message content or any embed attributes."""
            content = [message.content]

            # Add the content for all embed attributes
            for embed in message.embeds:
                content.append(embed.title)
                content.append(embed.description)
                content.append(embed.footer.text)
                content.append(embed.author.name)
                for field in embed.fields:
                    content.append(field.name)
                    content.append(field.value)

            # Get rid of empty attributes and turn it into a string
            content = [attr for attr in content if attr]
            content = "\n".join(content)

            # Now let's see if there's a regex match
            if not content:
                return False
            else:
                return bool(re.search(regex.lower(), content.lower()))

        # Is this an acceptable amount of messages to clean?
        if amount > CleanMessages.message_limit:
            embed = Embed(
                color=Colour(Colours.soft_red),
                title=random.choice(NEGATIVE_REPLIES),
                description=f"You cannot clean more than {CleanMessages.message_limit} messages."
            )
            await ctx.send(embed=embed)
            return

        # Are we already performing a clean?
        if self.cleaning:
            embed = Embed(
                color=Colour(Colours.soft_red),
                title=random.choice(NEGATIVE_REPLIES),
                description="Please wait for the currently ongoing clean operation to complete."
            )
            await ctx.send(embed=embed)
            return

        # Set up the correct predicate
        if bots_only:
            predicate = predicate_bots_only      # Delete messages from bots
        elif user:
            predicate = predicate_specific_user  # Delete messages from specific user
        elif regex:
            predicate = predicate_regex          # Delete messages that match regex
        else:
            predicate = None                     # Delete all messages

        # Default to using the invoking context's channel
        if not channel:
            channel = ctx.channel

        # Look through the history and retrieve message data
        messages = []
        message_ids = []
        self.cleaning = True
        invocation_deleted = False

        # To account for the invocation message, we index `amount + 1` messages.
        async for message in channel.history(limit=amount + 1):

            # If at any point the cancel command is invoked, we should stop.
            if not self.cleaning:
                return

            # Always start by deleting the invocation
            if not invocation_deleted:
                self.mod_log.ignore(Event.message_delete, message.id)
                await message.delete()
                invocation_deleted = True
                continue

            # If the message passes predicate, let's save it.
            if predicate is None or predicate(message):
                message_ids.append(message.id)
                messages.append(message)

        self.cleaning = False

        # We should ignore the ID's we stored, so we don't get mod-log spam.
        self.mod_log.ignore(Event.message_delete, *message_ids)

        # Use bulk delete to actually do the cleaning. It's far faster.
        await channel.purge(
            limit=amount,
            check=predicate
        )

        # Reverse the list to restore chronological order
        if messages:
            messages = list(reversed(messages))
            log_url = await self.mod_log.upload_log(messages, ctx.author.id)
        else:
            # Can't build an embed, nothing to clean!
            embed = Embed(
                color=Colour(Colours.soft_red),
                description="No matching messages could be found."
            )
            await ctx.send(embed=embed, delete_after=10)
            return

        # Build the embed and send it
        message = (
            f"**{len(message_ids)}** messages deleted in <#{channel.id}> by **{ctx.author.name}**\n\n"
            f"A log of the deleted messages can be found [here]({log_url})."
        )

        await self.mod_log.send_log_message(
            icon_url=Icons.message_bulk_delete,
            colour=Colour(Colours.soft_red),
            title="Bulk message delete",
            text=message,
            channel_id=Channels.mod_log,
        )

    @group(invoke_without_command=True, name="clean", aliases=["purge"])
    @with_role(*MODERATION_ROLES)
    async def clean_group(self, ctx: Context) -> None:
        """Commands for cleaning messages in channels."""
        await ctx.send_help(ctx.command)

    @clean_group.command(name="user", aliases=["users"])
    @with_role(*MODERATION_ROLES)
    async def clean_user(
        self,
        ctx: Context,
        user: User,
        amount: Optional[int] = 10,
        channel: TextChannel = None
    ) -> None:
        """Delete messages posted by the provided user, stop cleaning after traversing `amount` messages."""
        await self._clean_messages(amount, ctx, user=user, channel=channel)

    @clean_group.command(name="all", aliases=["everything"])
    @with_role(*MODERATION_ROLES)
    async def clean_all(
        self,
        ctx: Context,
        amount: Optional[int] = 10,
        channel: TextChannel = None
    ) -> None:
        """Delete all messages, regardless of poster, stop cleaning after traversing `amount` messages."""
        await self._clean_messages(amount, ctx, channel=channel)

    @clean_group.command(name="bots", aliases=["bot"])
    @with_role(*MODERATION_ROLES)
    async def clean_bots(
        self,
        ctx: Context,
        amount: Optional[int] = 10,
        channel: TextChannel = None
    ) -> None:
        """Delete all messages posted by a bot, stop cleaning after traversing `amount` messages."""
        await self._clean_messages(amount, ctx, bots_only=True, channel=channel)

    @clean_group.command(name="regex", aliases=["word", "expression"])
    @with_role(*MODERATION_ROLES)
    async def clean_regex(
        self,
        ctx: Context,
        regex: str,
        amount: Optional[int] = 10,
        channel: TextChannel = None
    ) -> None:
        """Delete all messages that match a certain regex, stop cleaning after traversing `amount` messages."""
        await self._clean_messages(amount, ctx, regex=regex, channel=channel)

    @clean_group.command(name="stop", aliases=["cancel", "abort"])
    @with_role(*MODERATION_ROLES)
    async def clean_cancel(self, ctx: Context) -> None:
        """If there is an ongoing cleaning process, attempt to immediately cancel it."""
        self.cleaning = False

        embed = Embed(
            color=Colour.blurple(),
            description="Clean interrupted."
        )
        await ctx.send(embed=embed, delete_after=10)


def setup(bot: Bot) -> None:
    """Load the Clean cog."""
    bot.add_cog(Clean(bot))
