import base64
import binascii
import logging
import re
import typing as t

from discord import Colour, Message, NotFound
from discord.ext.commands import Cog

from bot import utils
from bot.bot import Bot
from bot.constants import Channels, Colours, Event, Icons
from bot.exts.moderation.modlog import ModLog
from bot.utils.messages import format_user

log = logging.getLogger(__name__)

LOG_MESSAGE = (
    "Censored a seemingly valid token sent by {author} in {channel}, "
    "token was `{user_id}.{timestamp}.{hmac}`"
)
UNKNOWN_USER_LOG_MESSAGE = "Decoded user ID: `{user_id}` (Not present in server)."
KNOWN_USER_LOG_MESSAGE = (
    "Decoded user ID: `{user_id}` **(Present in server)**.\n"
    "This matches `{user_name}` and means this is likely a valid **{kind}** token."
)
DELETION_MESSAGE_TEMPLATE = (
    "Hey {mention}! I noticed you posted a seemingly valid Discord API "
    "token in your message and have removed your message. "
    "This means that your token has been **compromised**. "
    "Please change your token **immediately** at: "
    "<https://discordapp.com/developers/applications/me>\n\n"
    "Feel free to re-post it with the token removed. "
    "If you believe this was a mistake, please let us know!"
)
DISCORD_EPOCH = 1_420_070_400
TOKEN_EPOCH = 1_293_840_000

# Three parts delimited by dots: user ID, creation timestamp, HMAC.
# The HMAC isn't parsed further, but it's in the regex to ensure it at least exists in the string.
# Each part only matches base64 URL-safe characters.
# Padding has never been observed, but the padding character '=' is matched just in case.
TOKEN_RE = re.compile(r"([\w\-=]+)\.([\w\-=]+)\.([\w\-=]+)", re.ASCII)


class Token(t.NamedTuple):
    """A Discord Bot token."""

    user_id: str
    timestamp: str
    hmac: str


class TokenRemover(Cog):
    """Scans messages for potential discord.py bot tokens and removes them."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @property
    def mod_log(self) -> ModLog:
        """Get currently loaded ModLog cog instance."""
        return self.bot.get_cog("ModLog")

    @Cog.listener()
    async def on_message(self, msg: Message) -> None:
        """
        Check each message for a string that matches Discord's token pattern.

        See: https://discordapp.com/developers/docs/reference#snowflakes
        """
        # Ignore DMs; can't delete messages in there anyway.
        if not msg.guild or msg.author.bot:
            return

        found_token = self.find_token_in_message(msg)
        if found_token:
            await self.take_action(msg, found_token)

    @Cog.listener()
    async def on_message_edit(self, before: Message, after: Message) -> None:
        """
        Check each edit for a string that matches Discord's token pattern.

        See: https://discordapp.com/developers/docs/reference#snowflakes
        """
        await self.on_message(after)

    async def take_action(self, msg: Message, found_token: Token) -> None:
        """Remove the `msg` containing the `found_token` and send a mod log message."""
        self.mod_log.ignore(Event.message_delete, msg.id)

        try:
            await msg.delete()
        except NotFound:
            log.debug(f"Failed to remove token in message {msg.id}: message already deleted.")
            return

        await msg.channel.send(DELETION_MESSAGE_TEMPLATE.format(mention=msg.author.mention))

        log_message = self.format_log_message(msg, found_token)
        userid_message, mention_everyone = self.format_userid_log_message(msg, found_token)
        log.debug(log_message)

        # Send pretty mod log embed to mod-alerts
        await self.mod_log.send_log_message(
            icon_url=Icons.token_removed,
            colour=Colour(Colours.soft_red),
            title="Token removed!",
            text=log_message + "\n" + userid_message,
            thumbnail=msg.author.avatar_url_as(static_format="png"),
            channel_id=Channels.mod_alerts,
            ping_everyone=mention_everyone,
        )

        self.bot.stats.incr("tokens.removed_tokens")

    @classmethod
    def format_userid_log_message(cls, msg: Message, token: Token) -> t.Tuple[str, bool]:
        """
        Format the portion of the log message that includes details about the detected user ID.

        If the user is resolved to a member, the format includes the user ID, name, and the
        kind of user detected.

        If we resolve to a member and it is not a bot, we also return True to ping everyone.

        Returns a tuple of (log_message, mention_everyone)
        """
        user_id = cls.extract_user_id(token.user_id)
        user = msg.guild.get_member(user_id)

        if user:
            return KNOWN_USER_LOG_MESSAGE.format(
                user_id=user_id,
                user_name=str(user),
                kind="BOT" if user.bot else "USER",
            ), True
        else:
            return UNKNOWN_USER_LOG_MESSAGE.format(user_id=user_id), False

    @staticmethod
    def format_log_message(msg: Message, token: Token) -> str:
        """Return the generic portion of the log message to send for `token` being censored in `msg`."""
        return LOG_MESSAGE.format(
            author=format_user(msg.author),
            channel=msg.channel.mention,
            user_id=token.user_id,
            timestamp=token.timestamp,
            hmac='x' * (len(token.hmac) - 3) + token.hmac[-3:],
        )

    @classmethod
    def find_token_in_message(cls, msg: Message) -> t.Optional[Token]:
        """Return a seemingly valid token found in `msg` or `None` if no token is found."""
        # Use finditer rather than search to guard against method calls prematurely returning the
        # token check (e.g. `message.channel.send` also matches our token pattern)
        for match in TOKEN_RE.finditer(msg.content):
            token = Token(*match.groups())
            if (
                (cls.extract_user_id(token.user_id) is not None)
                and cls.is_valid_timestamp(token.timestamp)
                and cls.is_maybe_valid_hmac(token.hmac)
            ):
                # Short-circuit on first match
                return token

        # No matching substring
        return

    @staticmethod
    def extract_user_id(b64_content: str) -> t.Optional[int]:
        """Return a user ID integer from part of a potential token, or None if it couldn't be decoded."""
        b64_content = utils.pad_base64(b64_content)

        try:
            decoded_bytes = base64.urlsafe_b64decode(b64_content)
            string = decoded_bytes.decode('utf-8')
            if not (string.isascii() and string.isdigit()):
                # This case triggers if there are fancy unicode digits in the base64 encoding,
                # that means it's not a valid user id.
                return None
            return int(string)
        except (binascii.Error, ValueError):
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
        except (binascii.Error, ValueError) as e:
            log.debug(f"Failed to decode token timestamp '{b64_content}': {e}")
            return False

        # Seems like newer tokens don't need the epoch added, but add anyway since an upper bound
        # is not checked.
        if timestamp + TOKEN_EPOCH >= DISCORD_EPOCH:
            return True
        else:
            log.debug(f"Invalid token timestamp '{b64_content}': smaller than Discord epoch")
            return False

    @staticmethod
    def is_maybe_valid_hmac(b64_content: str) -> bool:
        """
        Determine if a given HMAC portion of a token is potentially valid.

        If the HMAC has 3 or less characters, it's probably a dummy value like "xxxxxxxxxx",
        and thus the token can probably be skipped.
        """
        unique = len(set(b64_content.lower()))
        if unique <= 3:
            log.debug(
                f"Considering the HMAC {b64_content} a dummy because it has {unique}"
                " case-insensitively unique characters"
            )
            return False
        else:
            return True


def setup(bot: Bot) -> None:
    """Load the TokenRemover cog."""
    bot.add_cog(TokenRemover(bot))
