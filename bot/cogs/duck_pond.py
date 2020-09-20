import logging
from typing import Union

import discord
from discord import Color, Embed, Member, Message, RawReactionActionEvent, User, errors
from discord.ext.commands import Cog

from bot import constants
from bot.bot import Bot
from bot.utils.messages import send_attachments
from bot.utils.webhooks import send_webhook

log = logging.getLogger(__name__)


class DuckPond(Cog):
    """Relays messages to #duck-pond whenever a certain number of duck reactions have been achieved."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.webhook_id = constants.Webhooks.duck_pond
        self.webhook = None
        self.bot.loop.create_task(self.fetch_webhook())

    async def fetch_webhook(self) -> None:
        """Fetches the webhook object, so we can post to it."""
        await self.bot.wait_until_guild_available()

        try:
            self.webhook = await self.bot.fetch_webhook(self.webhook_id)
        except discord.HTTPException:
            log.exception(f"Failed to fetch webhook with id `{self.webhook_id}`")

    @staticmethod
    def is_staff(member: Union[User, Member]) -> bool:
        """Check if a specific member or user is staff."""
        if hasattr(member, "roles"):
            for role in member.roles:
                if role.id in constants.STAFF_ROLES:
                    return True
        return False

    async def has_green_checkmark(self, message: Message) -> bool:
        """Check if the message has a green checkmark reaction."""
        for reaction in message.reactions:
            if reaction.emoji == "✅":
                async for user in reaction.users():
                    if user == self.bot.user:
                        return True
        return False

    @staticmethod
    def _is_duck_emoji(emoji: Union[str, discord.PartialEmoji, discord.Emoji]) -> bool:
        """Check if the emoji is a valid duck emoji."""
        if isinstance(emoji, str):
            return emoji == "🦆"
        else:
            return hasattr(emoji, "name") and emoji.name.startswith("ducky_")

    async def count_ducks(self, message: Message) -> int:
        """
        Count the number of ducks in the reactions of a specific message.

        Only counts ducks added by staff members.
        """
        duck_reactors = set()

        # iterate over all reactions
        for reaction in message.reactions:
            # check if the current reaction is a duck
            if not self._is_duck_emoji(reaction.emoji):
                continue

            # update the set of reactors with all staff reactors
            duck_reactors |= {user.id async for user in reaction.users() if self.is_staff(user)}

        return len(duck_reactors)

    async def relay_message(self, message: Message) -> None:
        """Relays the message's content and attachments to the duck pond channel."""
        if message.clean_content:
            await send_webhook(
                webhook=self.webhook,
                content=message.clean_content,
                username=message.author.display_name,
                avatar_url=message.author.avatar_url
            )

        if message.attachments:
            try:
                await send_attachments(message, self.webhook)
            except (errors.Forbidden, errors.NotFound):
                e = Embed(
                    description=":x: **This message contained an attachment, but it could not be retrieved**",
                    color=Color.red()
                )
                await send_webhook(
                    webhook=self.webhook,
                    embed=e,
                    username=message.author.display_name,
                    avatar_url=message.author.avatar_url
                )
            except discord.HTTPException:
                log.exception("Failed to send an attachment to the webhook")

        await message.add_reaction("✅")

    def _payload_has_duckpond_emoji(self, emoji: discord.PartialEmoji) -> bool:
        """Test if the RawReactionActionEvent payload contains a duckpond emoji."""
        if emoji.is_unicode_emoji():
            # For unicode PartialEmojis, the `name` attribute is just the string
            # representation of the emoji. This is what the helper method
            # expects, as unicode emojis show up as just a `str` instance when
            # inspecting the reactions attached to a message.
            emoji = emoji.name

        return self._is_duck_emoji(emoji)

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: RawReactionActionEvent) -> None:
        """
        Determine if a message should be sent to the duck pond.

        This will count the number of duck reactions on the message, and if this amount meets the
        amount of ducks specified in the config under duck_pond/threshold, it will
        send the message off to the duck pond.
        """
        # Was this reaction issued in a blacklisted channel?
        if payload.channel_id in constants.DuckPond.channel_blacklist:
            return

        # Is the emoji in the reaction a duck?
        if not self._payload_has_duckpond_emoji(payload.emoji):
            return

        channel = discord.utils.get(self.bot.get_all_channels(), id=payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        member = discord.utils.get(message.guild.members, id=payload.user_id)

        # Was the message sent by a human staff member?
        if not self.is_staff(message.author) or message.author.bot:
            return

        # Is the reactor a human staff member?
        if not self.is_staff(member) or member.bot:
            return

        # Does the message already have a green checkmark?
        if await self.has_green_checkmark(message):
            return

        # Time to count our ducks!
        duck_count = await self.count_ducks(message)

        # If we've got more than the required amount of ducks, send the message to the duck_pond.
        if duck_count >= constants.DuckPond.threshold:
            await self.relay_message(message)

    @Cog.listener()
    async def on_raw_reaction_remove(self, payload: RawReactionActionEvent) -> None:
        """Ensure that people don't remove the green checkmark from duck ponded messages."""
        channel = discord.utils.get(self.bot.get_all_channels(), id=payload.channel_id)

        # Prevent the green checkmark from being removed
        if payload.emoji.name == "✅":
            message = await channel.fetch_message(payload.message_id)
            duck_count = await self.count_ducks(message)
            if duck_count >= constants.DuckPond.threshold:
                await message.add_reaction("✅")


def setup(bot: Bot) -> None:
    """Load the DuckPond cog."""
    bot.add_cog(DuckPond(bot))
