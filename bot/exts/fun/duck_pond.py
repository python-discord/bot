import asyncio

import discord
from discord import Color, Embed, Message, RawReactionActionEvent, errors
from discord.ext.commands import Cog, Context, command

from bot import constants
from bot.bot import Bot
from bot.converters import MemberOrUser
from bot.log import get_logger
from bot.utils.checks import has_any_role
from bot.utils.messages import count_unique_users_reaction, send_attachments
from bot.utils.webhooks import send_webhook

log = get_logger(__name__)


class DuckPond(Cog):
    """Relays messages to #duck-pond whenever a certain number of duck reactions have been achieved."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.webhook_id = constants.Webhooks.duck_pond.id
        self.webhook = None
        self.ducked_messages = []
        self.relay_lock = None

    @staticmethod
    def is_staff(member: MemberOrUser) -> bool:
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
    def _is_duck_emoji(emoji: str | discord.PartialEmoji | discord.Emoji) -> bool:
        """Check if the emoji is a valid duck emoji."""
        if isinstance(emoji, str):
            return emoji == "🦆"
        return hasattr(emoji, "name") and emoji.name.startswith("ducky_")

    async def count_ducks(self, message: Message) -> int:
        """
        Count the number of ducks in the reactions of a specific message.

        Only counts ducks added by staff members.
        """
        return await count_unique_users_reaction(
            message,
            lambda r: self._is_duck_emoji(r.emoji),
            self.is_staff,
            False
        )

    async def relay_message(self, message: Message) -> None:
        """Relays the message's content and attachments to the duck pond channel."""
        if not self.webhook:
            await self.bot.wait_until_guild_available()
            # Fetching this can fail if using an invalid webhook id.
            # Letting this error bubble up is fine as it will cause an error log and sentry event.
            self.webhook = await self.bot.fetch_webhook(self.webhook_id)

        if message.clean_content:
            await send_webhook(
                webhook=self.webhook,
                content=message.clean_content,
                username=message.author.display_name,
                avatar_url=message.author.display_avatar.url
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
                    avatar_url=message.author.display_avatar.url
                )
            except discord.HTTPException:
                log.exception("Failed to send an attachment to the webhook")

    async def locked_relay(self, message: Message) -> bool:
        """Relay a message after obtaining the relay lock."""
        if self.relay_lock is None:
            # Lazily load the lock to ensure it's created within the
            # appropriate event loop.
            self.relay_lock = asyncio.Lock()

        async with self.relay_lock:
            # check if the message has a checkmark after acquiring the lock
            if await self.has_green_checkmark(message):
                return False

            # relay the message
            await self.relay_message(message)

            # add a green checkmark to indicate that the message was relayed
            await message.add_reaction("✅")
        return True

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
        # Ignore other guilds and DMs.
        if payload.guild_id != constants.Guild.id:
            return

        # Was this reaction issued in a blacklisted channel?
        if payload.channel_id in constants.DuckPond.channel_blacklist:
            return

        # Is the emoji in the reaction a duck?
        if not self._payload_has_duckpond_emoji(payload.emoji):
            return

        await self.bot.wait_until_guild_available()
        guild = self.bot.get_guild(payload.guild_id)
        channel = guild.get_channel_or_thread(payload.channel_id)
        if channel is None:
            return

        # Was the message sent in a channel Helpers can see?
        helper_role = guild.get_role(constants.Roles.helpers)
        if not channel.permissions_for(helper_role).view_channel:
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            return  # Message was deleted.

        member = discord.utils.get(message.guild.members, id=payload.user_id)
        if not member:
            return  # Member left or wasn't in the cache.

        # Was the message sent by a human staff member?
        if not self.is_staff(message.author) or message.author.bot:
            return

        # Is the reactor a human staff member?
        if not self.is_staff(member) or member.bot:
            return

        # Time to count our ducks!
        duck_count = await self.count_ducks(message)

        # If we've got more than the required amount of ducks, send the message to the duck_pond.
        if duck_count >= constants.DuckPond.threshold and message.id not in self.ducked_messages:
            self.ducked_messages.append(message.id)
            await self.locked_relay(message)

    @Cog.listener()
    async def on_raw_reaction_remove(self, payload: RawReactionActionEvent) -> None:
        """Ensure that people don't remove the green checkmark from duck ponded messages."""
        # Ignore other guilds and DMs.
        if payload.guild_id != constants.Guild.id:
            return

        channel = discord.utils.get(self.bot.get_all_channels(), id=payload.channel_id)
        if channel is None:
            return

        # Prevent the green checkmark from being removed
        if payload.emoji.name == "✅":
            message = await channel.fetch_message(payload.message_id)
            duck_count = await self.count_ducks(message)
            if duck_count >= constants.DuckPond.threshold:
                await message.add_reaction("✅")

    @command(name="duckify", aliases=("duckpond", "pondify"))
    @has_any_role(constants.Roles.admins)
    async def duckify(self, ctx: Context, message: Message) -> None:
        """Relay a message to the duckpond, no ducks required!"""
        if await self.locked_relay(message):
            await ctx.message.add_reaction("🦆")
        else:
            await ctx.message.add_reaction("❌")


async def setup(bot: Bot) -> None:
    """Load the DuckPond cog."""
    await bot.add_cog(DuckPond(bot))
