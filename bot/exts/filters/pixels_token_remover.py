import logging
import re
import typing as t

from discord import Colour, Message, NotFound
from discord.ext.commands import Cog

from bot.bot import Bot
from bot.constants import Channels, Colours, Event, Icons
from bot.exts.moderation.modlog import ModLog
from bot.utils.messages import format_user

log = logging.getLogger(__name__)

LOG_MESSAGE = "Censored a valid Pixels token sent by {author} in {channel}, token was `{token}`"
DELETION_MESSAGE_TEMPLATE = (
    "Hey {mention}! I noticed you posted a valid Pixels API "
    "token in your message and have removed your message. "
    "This means that your token has been **compromised**. "
    "I have taken the liberty of invalidating the token for you. "
    "You can go to <https://pixels.pythondiscord.com/authorize> to get a new key."
)

PIXELS_TOKEN_RE = re.compile(r"[A-Za-z0-9-_=]{30,}\.[A-Za-z0-9-_=]{50,}\.[A-Za-z0-9-_.+\=]{30,}")


class PixelsTokenRemover(Cog):
    """Scans messages for Pixels API tokens, removes and invalidates them."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @property
    def mod_log(self) -> ModLog:
        """Get currently loaded ModLog cog instance."""
        return self.bot.get_cog("ModLog")

    @Cog.listener()
    async def on_message(self, msg: Message) -> None:
        """Check each message for a string that matches the RS-256 token pattern."""
        # Ignore DMs; can't delete messages in there anyway.
        if not msg.guild or msg.author.bot:
            return

        found_token = await self.find_token_in_message(msg)
        if found_token:
            await self.take_action(msg, found_token)

    @Cog.listener()
    async def on_message_edit(self, before: Message, after: Message) -> None:
        """Check each edit for a string that matches the RS-256 token pattern."""
        await self.on_message(after)

    async def take_action(self, msg: Message, found_token: str) -> None:
        """Remove the `msg` containing the `found_token` and send a mod log message."""
        self.mod_log.ignore(Event.message_delete, msg.id)

        try:
            await msg.delete()
        except NotFound:
            log.debug(f"Failed to remove token in message {msg.id}: message already deleted.")
            return

        await msg.channel.send(DELETION_MESSAGE_TEMPLATE.format(mention=msg.author.mention))

        log_message = self.format_log_message(msg, found_token)
        log.debug(log_message)

        # Send pretty mod log embed to mod-alerts
        await self.mod_log.send_log_message(
            icon_url=Icons.token_removed,
            colour=Colour(Colours.soft_red),
            title="Token removed!",
            text=log_message,
            thumbnail=msg.author.avatar_url_as(static_format="png"),
            channel_id=Channels.mod_alerts,
            ping_everyone=False,
        )

        self.bot.stats.incr("tokens.removed_pixels_tokens")

    @staticmethod
    def format_log_message(msg: Message, token: str) -> str:
        """Return the generic portion of the log message to send for `token` being censored in `msg`."""
        return LOG_MESSAGE.format(
            author=format_user(msg.author),
            channel=msg.channel.mention,
            token=token
        )

    async def find_token_in_message(self, msg: Message) -> t.Optional[str]:
        """Return a seemingly valid token found in `msg` or `None` if no token is found."""
        # Use finditer rather than search to guard against method calls prematurely returning the
        # token check (e.g. `message.channel.send` also matches our token pattern)
        for match in PIXELS_TOKEN_RE.finditer(msg.content):
            auth_header = {"Authorization": f"Bearer {match[0]}"}
            async with self.bot.http_session.delete("https://pixels.pythondiscord.com/token", headers=auth_header) as r:
                if r.status == 204:
                    # Short curcuit on first match.
                    return match[0]

        # No matching substring
        return


def setup(bot: Bot) -> None:
    """Load the PixelsTokenRemover cog."""
    bot.add_cog(PixelsTokenRemover(bot))
