import logging
import re
from typing import Optional, Union

import discord.errors
from dateutil.relativedelta import relativedelta
from discord import Colour, DMChannel, Member, Message, TextChannel
from discord.ext.commands import Cog
from discord.utils import escape_markdown

from bot.bot import Bot
from bot.cogs.moderation import ModLog
from bot.constants import (
    Channels, Colours,
    Filter, Icons, URLs
)

log = logging.getLogger(__name__)

INVITE_RE = re.compile(
    r"(?:discord(?:[\.,]|dot)gg|"                     # Could be discord.gg/
    r"discord(?:[\.,]|dot)com(?:\/|slash)invite|"     # or discord.com/invite/
    r"discordapp(?:[\.,]|dot)com(?:\/|slash)invite|"  # or discordapp.com/invite/
    r"discord(?:[\.,]|dot)me|"                        # or discord.me
    r"discord(?:[\.,]|dot)io"                         # or discord.io.
    r")(?:[\/]|slash)"                                # / or 'slash'
    r"([a-zA-Z0-9]+)",                                # the invite code itself
    flags=re.IGNORECASE
)

SPOILER_RE = re.compile(r"(\|\|.+?\|\|)", re.DOTALL)
URL_RE = re.compile(r"(https?://[^\s]+)", flags=re.IGNORECASE)
ZALGO_RE = re.compile(r"[\u0300-\u036F\u0489]")

WORD_WATCHLIST_PATTERNS = [
    re.compile(fr'\b{expression}\b', flags=re.IGNORECASE) for expression in Filter.word_watchlist
]
TOKEN_WATCHLIST_PATTERNS = [
    re.compile(fr'{expression}', flags=re.IGNORECASE) for expression in Filter.token_watchlist
]


def expand_spoilers(text: str) -> str:
    """Return a string containing all interpretations of a spoilered message."""
    split_text = SPOILER_RE.split(text)
    return ''.join(
        split_text[0::2] + split_text[1::2] + split_text
    )


class Filtering(Cog):
    """Filtering out invites, blacklisting domains, and warning us of certain regular expressions."""

    def __init__(self, bot: Bot):
        self.bot = bot

        staff_mistake_str = "If you believe this was a mistake, please let staff know!"
        self.filters = {
            "filter_zalgo": {
                "enabled": Filter.filter_zalgo,
                "function": self._has_zalgo,
                "type": "filter",
                "content_only": True,
                "user_notification": Filter.notify_user_zalgo,
                "notification_msg": (
                    "Your post has been removed for abusing Unicode character rendering (aka Zalgo text). "
                    f"{staff_mistake_str}"
                )
            },
            "filter_invites": {
                "enabled": Filter.filter_invites,
                "function": self._has_invites,
                "type": "filter",
                "content_only": True,
                "user_notification": Filter.notify_user_invites,
                "notification_msg": (
                    f"Per Rule 6, your invite link has been removed. {staff_mistake_str}\n\n"
                    r"Our server rules can be found here: <https://pythondiscord.com/pages/rules>"
                )
            },
            "filter_domains": {
                "enabled": Filter.filter_domains,
                "function": self._has_urls,
                "type": "filter",
                "content_only": True,
                "user_notification": Filter.notify_user_domains,
                "notification_msg": (
                    f"Your URL has been removed because it matched a blacklisted domain. {staff_mistake_str}"
                )
            },
            "watch_rich_embeds": {
                "enabled": Filter.watch_rich_embeds,
                "function": self._has_rich_embed,
                "type": "watchlist",
                "content_only": False,
            },
            "watch_words": {
                "enabled": Filter.watch_words,
                "function": self._has_watchlist_words,
                "type": "watchlist",
                "content_only": True,
            },
            "watch_tokens": {
                "enabled": Filter.watch_tokens,
                "function": self._has_watchlist_tokens,
                "type": "watchlist",
                "content_only": True,
            },
        }

    @property
    def mod_log(self) -> ModLog:
        """Get currently loaded ModLog cog instance."""
        return self.bot.get_cog("ModLog")

    @Cog.listener()
    async def on_message(self, msg: Message) -> None:
        """Invoke message filter for new messages."""
        await self._filter_message(msg)

    @Cog.listener()
    async def on_message_edit(self, before: Message, after: Message) -> None:
        """
        Invoke message filter for message edits.

        If there have been multiple edits, calculate the time delta from the previous edit.
        """
        if not before.edited_at:
            delta = relativedelta(after.edited_at, before.created_at).microseconds
        else:
            delta = relativedelta(after.edited_at, before.edited_at).microseconds
        await self._filter_message(after, delta)

    async def _filter_message(self, msg: Message, delta: Optional[int] = None) -> None:
        """Filter the input message to see if it violates any of our rules, and then respond accordingly."""
        # Should we filter this message?
        role_whitelisted = False

        if type(msg.author) is Member:  # Only Member has roles, not User.
            for role in msg.author.roles:
                if role.id in Filter.role_whitelist:
                    role_whitelisted = True

        filter_message = (
            msg.channel.id not in Filter.channel_whitelist and not  # Channel not in whitelist
            role_whitelisted and not                                # Role not in whitelist
            msg.author.bot                                          # Author not a bot
        )

        # If none of the above, we can start filtering.
        if filter_message:
            for filter_name, _filter in self.filters.items():
                # Is this specific filter enabled in the config?
                if _filter["enabled"]:
                    # Double trigger check for the embeds filter
                    if filter_name == "watch_rich_embeds":
                        # If the edit delta is less than 0.001 seconds, then we're probably dealing
                        # with a double filter trigger.
                        if delta is not None and delta < 100:
                            continue

                    # Does the filter only need the message content or the full message?
                    if _filter["content_only"]:
                        match = await _filter["function"](msg.content)
                    else:
                        match = await _filter["function"](msg)

                    if match:
                        # If this is a filter (not a watchlist), we should delete the message.
                        if _filter["type"] == "filter":
                            try:
                                # Embeds (can?) trigger both the `on_message` and `on_message_edit`
                                # event handlers, triggering filtering twice for the same message.
                                #
                                # If `on_message`-triggered filtering already deleted the message
                                # then `on_message_edit`-triggered filtering will raise exception
                                # since the message no longer exists.
                                #
                                # In addition, to avoid sending two notifications to the user, the
                                # logs, and mod_alert, we return if the message no longer exists.
                                await msg.delete()
                            except discord.errors.NotFound:
                                return

                            # Notify the user if the filter specifies
                            if _filter["user_notification"]:
                                await self.notify_member(msg.author, _filter["notification_msg"], msg.channel)

                        if isinstance(msg.channel, DMChannel):
                            channel_str = "via DM"
                        else:
                            channel_str = f"in {msg.channel.mention}"

                        # Word and match stats for watch_words and watch_tokens
                        if filter_name in ("watch_words", "watch_tokens"):
                            surroundings = match.string[max(match.start() - 10, 0): match.end() + 10]
                            message_content = (
                                f"**Match:** '{match[0]}'\n"
                                f"**Location:** '...{escape_markdown(surroundings)}...'\n"
                                f"\n**Original Message:**\n{escape_markdown(msg.content)}"
                            )
                        else:  # Use content of discord Message
                            message_content = msg.content

                        message = (
                            f"The {filter_name} {_filter['type']} was triggered "
                            f"by **{msg.author}** "
                            f"(`{msg.author.id}`) {channel_str} with [the "
                            f"following message]({msg.jump_url}):\n\n"
                            f"{message_content}"
                        )

                        log.debug(message)

                        additional_embeds = None
                        additional_embeds_msg = None

                        if filter_name == "filter_invites":
                            additional_embeds = []
                            for invite, data in match.items():
                                embed = discord.Embed(description=(
                                    f"**Members:**\n{data['members']}\n"
                                    f"**Active:**\n{data['active']}"
                                ))
                                embed.set_author(name=data["name"])
                                embed.set_thumbnail(url=data["icon"])
                                embed.set_footer(text=f"Guild Invite Code: {invite}")
                                additional_embeds.append(embed)
                            additional_embeds_msg = "For the following guild(s):"

                        elif filter_name == "watch_rich_embeds":
                            additional_embeds = msg.embeds
                            additional_embeds_msg = "With the following embed(s):"

                        # Send pretty mod log embed to mod-alerts
                        await self.mod_log.send_log_message(
                            icon_url=Icons.filtering,
                            colour=Colour(Colours.soft_red),
                            title=f"{_filter['type'].title()} triggered!",
                            text=message,
                            thumbnail=msg.author.avatar_url_as(static_format="png"),
                            channel_id=Channels.mod_alerts,
                            ping_everyone=Filter.ping_everyone,
                            additional_embeds=additional_embeds,
                            additional_embeds_msg=additional_embeds_msg
                        )

                        break  # We don't want multiple filters to trigger

    @staticmethod
    async def _has_watchlist_words(text: str) -> Union[bool, re.Match]:
        """
        Returns True if the text contains one of the regular expressions from the word_watchlist in our filter config.

        Only matches words with boundaries before and after the expression.
        """
        if SPOILER_RE.search(text):
            text = expand_spoilers(text)
        for regex_pattern in WORD_WATCHLIST_PATTERNS:
            match = regex_pattern.search(text)
            if match:
                return match  # match objects always have a boolean value of True

        return False

    @staticmethod
    async def _has_watchlist_tokens(text: str) -> Union[bool, re.Match]:
        """
        Returns True if the text contains one of the regular expressions from the token_watchlist in our filter config.

        This will match the expression even if it does not have boundaries before and after.
        """
        for regex_pattern in TOKEN_WATCHLIST_PATTERNS:
            match = regex_pattern.search(text)
            if match:

                # Make sure it's not a URL
                if not URL_RE.search(text):
                    return match  # match objects always have a boolean value of True

        return False

    @staticmethod
    async def _has_urls(text: str) -> bool:
        """Returns True if the text contains one of the blacklisted URLs from the config file."""
        if not URL_RE.search(text):
            return False

        text = text.lower()

        for url in Filter.domain_blacklist:
            if url.lower() in text:
                return True

        return False

    @staticmethod
    async def _has_zalgo(text: str) -> bool:
        """
        Returns True if the text contains zalgo characters.

        Zalgo range is \u0300 – \u036F and \u0489.
        """
        return bool(ZALGO_RE.search(text))

    async def _has_invites(self, text: str) -> Union[dict, bool]:
        """
        Checks if there's any invites in the text content that aren't in the guild whitelist.

        If any are detected, a dictionary of invite data is returned, with a key per invite.
        If none are detected, False is returned.

        Attempts to catch some of common ways to try to cheat the system.
        """
        # Remove backslashes to prevent escape character aroundfuckery like
        # discord\.gg/gdudes-pony-farm
        text = text.replace("\\", "")

        invites = INVITE_RE.findall(text)
        invite_data = dict()
        for invite in invites:
            if invite in invite_data:
                continue

            response = await self.bot.http_session.get(
                f"{URLs.discord_invite_api}/{invite}", params={"with_counts": "true"}
            )
            response = await response.json()
            guild = response.get("guild")
            if guild is None:
                # Lack of a "guild" key in the JSON response indicates either an group DM invite, an
                # expired invite, or an invalid invite. The API does not currently differentiate
                # between invalid and expired invites
                return True

            guild_id = int(guild.get("id"))

            if guild_id not in Filter.guild_invite_whitelist:
                guild_icon_hash = guild["icon"]
                guild_icon = (
                    "https://cdn.discordapp.com/icons/"
                    f"{guild_id}/{guild_icon_hash}.png?size=512"
                )

                invite_data[invite] = {
                    "name": guild["name"],
                    "icon": guild_icon,
                    "members": response["approximate_member_count"],
                    "active": response["approximate_presence_count"]
                }

        return invite_data if invite_data else False

    @staticmethod
    async def _has_rich_embed(msg: Message) -> bool:
        """Determines if `msg` contains any rich embeds not auto-generated from a URL."""
        if msg.embeds:
            for embed in msg.embeds:
                if embed.type == "rich":
                    urls = URL_RE.findall(msg.content)
                    if not embed.url or embed.url not in urls:
                        # If `embed.url` does not exist or if `embed.url` is not part of the content
                        # of the message, it's unlikely to be an auto-generated embed by Discord.
                        return True
                    else:
                        log.trace(
                            "Found a rich embed sent by a regular user account, "
                            "but it was likely just an automatic URL embed."
                        )
                        return False
        return False

    async def notify_member(self, filtered_member: Member, reason: str, channel: TextChannel) -> None:
        """
        Notify filtered_member about a moderation action with the reason str.

        First attempts to DM the user, fall back to in-channel notification if user has DMs disabled
        """
        try:
            await filtered_member.send(reason)
        except discord.errors.Forbidden:
            await channel.send(f"{filtered_member.mention} {reason}")


def setup(bot: Bot) -> None:
    """Load the Filtering cog."""
    bot.add_cog(Filtering(bot))
