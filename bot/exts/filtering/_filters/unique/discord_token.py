import base64
import re
from collections.abc import Callable, Coroutine
from typing import ClassVar, NamedTuple

import discord
from pydantic import BaseModel, Field
from pydis_core.utils.logging import get_logger
from pydis_core.utils.members import get_or_fetch_member

import bot
from bot import constants, utils
from bot.constants import Guild
from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filters.filter import UniqueFilter
from bot.exts.filtering._utils import resolve_mention
from bot.exts.moderation.modlog import ModLog
from bot.utils.messages import format_user

log = get_logger(__name__)


LOG_MESSAGE = (
    "Censored a seemingly valid token sent by {author} in {channel}. "
    "Token was: `{user_id}.{timestamp}.{hmac}`."
)
UNKNOWN_USER_LOG_MESSAGE = "Decoded user ID: `{user_id}` (Not present in server)."
KNOWN_USER_LOG_MESSAGE = (
    "Decoded user ID: `{user_id}` **(Present in server)**.\n"
    "This matches `{user_name}` and means this is likely a valid **{kind}** token."
)
DISCORD_EPOCH = 1_420_070_400
TOKEN_EPOCH = 1_293_840_000

# Three parts delimited by dots: user ID, creation timestamp, HMAC.
# The HMAC isn't parsed further, but it's in the regex to ensure it at least exists in the string.
# Each part only matches base64 URL-safe characters.
# These regexes were taken from discord-developers, which are used by the client itself.
TOKEN_RE = re.compile(r"([\w-]{10,})\.([\w-]{5,})\.([\w-]{10,})")


class ExtraDiscordTokenSettings(BaseModel):
    """Extra settings for who should be pinged when a Discord token is detected."""

    pings_for_bot_description: ClassVar[str] = "A sequence. Who should be pinged if the token found belongs to a bot."
    pings_for_user_description: ClassVar[str] = "A sequence. Who should be pinged if the token found belongs to a user."

    pings_for_bot: set[str] = Field(default_factory=set)
    pings_for_user: set[str] = Field(default_factory=lambda: {"Moderators"})


class Token(NamedTuple):
    """A Discord Bot token."""

    user_id: str
    timestamp: str
    hmac: str


class DiscordTokenFilter(UniqueFilter):
    """Scans messages for potential discord client tokens and removes them."""

    name = "discord_token"
    events = (Event.MESSAGE, Event.MESSAGE_EDIT, Event.SNEKBOX)
    extra_fields_type = ExtraDiscordTokenSettings

    @property
    def mod_log(self) -> ModLog | None:
        """Get currently loaded ModLog cog instance."""
        return bot.instance.get_cog("ModLog")

    async def triggered_on(self, ctx: FilterContext) -> bool:
        """Return whether the message contains Discord client tokens."""
        found_token = self.find_token_in_message(ctx.content)
        if not found_token:
            return False

        if ctx.message and (mod_log := self.mod_log):
            mod_log.ignore(constants.Event.message_delete, ctx.message.id)
        ctx.content = ctx.content.replace(found_token.hmac, self.censor_hmac(found_token.hmac))
        ctx.additional_actions.append(self._create_token_alert_embed_wrapper(found_token))
        return True

    def _create_token_alert_embed_wrapper(self, found_token: Token) -> Callable[[FilterContext], Coroutine]:
        """Create the action to perform when an alert should be sent for a message containing a Discord token."""
        async def _create_token_alert_embed(ctx: FilterContext) -> None:
            """Add an alert embed to the context with info about the token sent."""
            userid_message, is_user = await self.format_userid_log_message(found_token)
            log_message = self.format_log_message(ctx.author, ctx.channel, found_token)
            log.debug(log_message)

            if is_user:
                mentions = map(resolve_mention, self.extra_fields.pings_for_user)
                color = discord.Colour.red()
            else:
                mentions = map(resolve_mention, self.extra_fields.pings_for_bot)
                color = discord.Colour.blue()
            unmentioned = [mention for mention in mentions if mention not in ctx.alert_content]
            if unmentioned:
                ctx.alert_content = f"{' '.join(unmentioned)} {ctx.alert_content}"
            ctx.alert_embeds.append(discord.Embed(colour=color, description=userid_message))

        return _create_token_alert_embed

    @classmethod
    async def format_userid_log_message(cls, token: Token) -> tuple[str, bool]:
        """
        Format the portion of the log message that includes details about the detected user ID.

        If the user is resolved to a member, the format includes the user ID, name, and the
        kind of user detected.
        If it is resolved to a user or a member, and it is not a bot, also return True.
        Returns a tuple of (log_message, is_user)
        """
        user_id = cls.extract_user_id(token.user_id)
        guild = bot.instance.get_guild(Guild.id)
        user = await get_or_fetch_member(guild, user_id)

        if user:
            return KNOWN_USER_LOG_MESSAGE.format(
                user_id=user_id,
                user_name=str(user),
                kind="BOT" if user.bot else "USER",
            ), True
        return UNKNOWN_USER_LOG_MESSAGE.format(user_id=user_id), False

    @staticmethod
    def censor_hmac(hmac: str) -> str:
        """Return a censored version of the hmac."""
        return "x" * (len(hmac) - 3) + hmac[-3:]

    @classmethod
    def format_log_message(cls, author: discord.User, channel: discord.abc.GuildChannel, token: Token) -> str:
        """Return the generic portion of the log message to send for `token` being censored in `msg`."""
        return LOG_MESSAGE.format(
            author=format_user(author),
            channel=channel.mention,
            user_id=token.user_id,
            timestamp=token.timestamp,
            hmac=cls.censor_hmac(token.hmac),
        )

    @classmethod
    def find_token_in_message(cls, content: str) -> Token | None:
        """Return a seemingly valid token found in `content` or `None` if no token is found."""
        # Use finditer rather than search to guard against method calls prematurely returning the
        # token check (e.g. `message.channel.send` also matches our token pattern)
        for match in TOKEN_RE.finditer(content):
            token = Token(*match.groups())
            if (
                (cls.extract_user_id(token.user_id) is not None)
                and cls.is_valid_timestamp(token.timestamp)
                and cls.is_maybe_valid_hmac(token.hmac)
            ):
                # Short-circuit on first match
                return token

        # No matching substring
        return None

    @staticmethod
    def extract_user_id(b64_content: str) -> int | None:
        """Return a user ID integer from part of a potential token, or None if it couldn't be decoded."""
        b64_content = utils.pad_base64(b64_content)

        try:
            decoded_bytes = base64.urlsafe_b64decode(b64_content)
            string = decoded_bytes.decode("utf-8")
            if not (string.isascii() and string.isdigit()):
                # This case triggers if there are fancy unicode digits in the base64 encoding,
                # that means it's not a valid user id.
                return None
            return int(string)
        except ValueError:
            return None

    @staticmethod
    def is_valid_timestamp(b64_content: str) -> bool:
        """
        Return True if `b64_content` decodes to a valid timestamp.

        If the timestamp is greater than the Discord epoch, it's probably valid.
        See: https://i.imgur.com/7WdehGn.png
        """
        b64_content = utils.pad_base64(b64_content)

        try:
            decoded_bytes = base64.urlsafe_b64decode(b64_content)
            timestamp = int.from_bytes(decoded_bytes, byteorder="big")
        except ValueError as e:
            log.debug(f"Failed to decode token timestamp '{b64_content}': {e}")
            return False

        # Seems like newer tokens don't need the epoch added, but add anyway since an upper bound
        # is not checked.
        if timestamp + TOKEN_EPOCH >= DISCORD_EPOCH:
            return True

        log.debug(f"Invalid token timestamp '{b64_content}': smaller than Discord epoch")
        return False

    @staticmethod
    def is_maybe_valid_hmac(b64_content: str) -> bool:
        """
        Determine if a given HMAC portion of a token is potentially valid.

        If the HMAC has 3 or fewer characters, it's probably a dummy value like "xxxxxxxxxx",
        and thus the token can probably be skipped.
        """
        unique = len(set(b64_content.lower()))
        if unique <= 3:
            log.debug(
                f"Considering the HMAC {b64_content} a dummy because it has {unique}"
                " case-insensitively unique characters"
            )
            return False
        return True
