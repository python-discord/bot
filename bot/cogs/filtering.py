import logging
import re
from typing import Optional, Union

import discord.errors
from dateutil.relativedelta import relativedelta
from discord import Colour, DMChannel, Member, Message, TextChannel
from discord.ext.commands import Bot

from bot.cogs.modlog import ModLog
from bot.constants import (
    Channels, Colours, DEBUG_MODE,
    Filter, Icons, URLs
)

log = logging.getLogger(__name__)

INVITE_RE = (
    r"(?:discord(?:[\.,]|dot)gg|"                     # Could be discord.gg/
    r"discord(?:[\.,]|dot)com(?:\/|slash)invite|"     # or discord.com/invite/
    r"discordapp(?:[\.,]|dot)com(?:\/|slash)invite|"  # or discordapp.com/invite/
    r"discord(?:[\.,]|dot)me|"                        # or discord.me
    r"discord(?:[\.,]|dot)io"                         # or discord.io.
    r")(?:[\/]|slash)"                                # / or 'slash'
    r"([a-zA-Z0-9]+)"                                 # the invite code itself
)

URL_RE = r"(https?://[^\s]+)"
ZALGO_RE = r"[\u0300-\u036F\u0489]"
RETARDED_RE = r"(re+)tar+(d+|t+)(ed)?"
SELF_DEPRECATION_RE = fr"((i'?m)|(i am)|(it'?s)|(it is)) (.+? )?{RETARDED_RE}"
RETARDED_QUESTIONS_RE = fr"{RETARDED_RE} questions?"


class Filtering:
    """
    Filtering out invites, blacklisting domains,
    and warning us of certain regular expressions
    """

    def __init__(self, bot: Bot):
        self.bot = bot

        _staff_mistake_str = "If you believe this was a mistake, please let staff know!"
        self.filters = {
            "filter_zalgo": {
                "enabled": Filter.filter_zalgo,
                "function": self._has_zalgo,
                "type": "filter",
                "content_only": True,
                "user_notification": Filter.notify_user_zalgo,
                "notification_msg": (
                    "Your post has been removed for abusing Unicode character rendering (aka Zalgo text). "
                    f"{_staff_mistake_str}"
                )
            },
            "filter_invites": {
                "enabled": Filter.filter_invites,
                "function": self._has_invites,
                "type": "filter",
                "content_only": True,
                "user_notification": Filter.notify_user_invites,
                "notification_msg": (
                    f"Per Rule 10, your invite link has been removed. {_staff_mistake_str}\n\n"
                    r"Our server rules can be found here: <https://pythondiscord.com/about/rules>"
                )
            },
            "filter_domains": {
                "enabled": Filter.filter_domains,
                "function": self._has_urls,
                "type": "filter",
                "content_only": True,
                "user_notification": Filter.notify_user_domains,
                "notification_msg": (
                    f"Your URL has been removed because it matched a blacklisted domain. {_staff_mistake_str}"
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
        return self.bot.get_cog("ModLog")

    async def on_message(self, msg: Message):
        await self._filter_message(msg)

    async def on_message_edit(self, before: Message, after: Message):
        if not before.edited_at:
            delta = relativedelta(after.edited_at, before.created_at).microseconds
        else:
            delta = None
        await self._filter_message(after, delta)

    async def _filter_message(self, msg: Message, delta: Optional[int] = None):
        """
        Whenever a message is sent or edited,
        run it through our filters to see if it
        violates any of our rules, and then respond
        accordingly.
        """

        # Should we filter this message?
        role_whitelisted = False

        if type(msg.author) is Member:  # Only Member has roles, not User.
            for role in msg.author.roles:
                if role.id in Filter.role_whitelist:
                    role_whitelisted = True

        filter_message = (
            msg.channel.id not in Filter.channel_whitelist  # Channel not in whitelist
            and not role_whitelisted                        # Role not in whitelist
            and not msg.author.bot                          # Author not a bot
        )

        # If we're running the bot locally, ignore role whitelist and only listen to #dev-test
        if DEBUG_MODE:
            filter_message = not msg.author.bot and msg.channel.id == Channels.devtest

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
                            return

                    # Does the filter only need the message content or the full message?
                    if _filter["content_only"]:
                        triggered = await _filter["function"](msg.content)
                    else:
                        triggered = await _filter["function"](msg)

                    if triggered:
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

                        message = (
                            f"The {filter_name} {_filter['type']} was triggered "
                            f"by **{msg.author.name}#{msg.author.discriminator}** "
                            f"(`{msg.author.id}`) {channel_str} with [the "
                            f"following message]({msg.jump_url}):\n\n"
                            f"{msg.content}"
                        )

                        log.debug(message)

                        additional_embeds = None
                        additional_embeds_msg = None

                        if filter_name == "filter_invites":
                            additional_embeds = []
                            for invite, data in triggered.items():
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
    async def _has_watchlist_words(text: str) -> bool:
        """
        Returns True if the text contains
        one of the regular expressions from the
        word_watchlist in our filter config.

        Only matches words with boundaries before
        and after the expression.
        """

        for expression in Filter.word_watchlist:
            if re.search(fr"\b{expression}\b", text, re.IGNORECASE):

                # Special handling for `retarded`
                if expression == RETARDED_RE:

                    # stuff like "I'm just retarded"
                    if re.search(SELF_DEPRECATION_RE, text, re.IGNORECASE):
                        return False

                    # stuff like "sorry for all the retarded questions"
                    elif re.search(RETARDED_QUESTIONS_RE, text, re.IGNORECASE):
                        return False

                return True

        return False

    @staticmethod
    async def _has_watchlist_tokens(text: str) -> bool:
        """
        Returns True if the text contains
        one of the regular expressions from the
        token_watchlist in our filter config.

        This will match the expression even if it
        does not have boundaries before and after
        """

        for expression in Filter.token_watchlist:
            if re.search(fr"{expression}", text, re.IGNORECASE):

                # Make sure it's not a URL
                if not re.search(URL_RE, text, re.IGNORECASE):
                    return True

        return False

    @staticmethod
    async def _has_urls(text: str) -> bool:
        """
        Returns True if the text contains one of
        the blacklisted URLs from the config file.
        """

        if not re.search(URL_RE, text, re.IGNORECASE):
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

        return bool(re.search(ZALGO_RE, text))

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

        invites = re.findall(INVITE_RE, text, re.IGNORECASE)
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
    async def _has_rich_embed(msg: Message):
        """
        Returns True if any of the embeds in the message are of type 'rich', but are not twitter
        embeds. Returns False otherwise.
        """
        if msg.embeds:
            for embed in msg.embeds:
                if embed.type == "rich" and (not embed.url or "twitter.com" not in embed.url):
                    return True
        return False

    async def notify_member(self, filtered_member: Member, reason: str, channel: TextChannel):
        """
        Notify filtered_member about a moderation action with the reason str

        First attempts to DM the user, fall back to in-channel notification if user has DMs disabled
        """

        try:
            await filtered_member.send(reason)
        except discord.errors.Forbidden:
            await channel.send(f"{filtered_member.mention} {reason}")


def setup(bot: Bot):
    bot.add_cog(Filtering(bot))
    log.info("Cog loaded: Filtering")
