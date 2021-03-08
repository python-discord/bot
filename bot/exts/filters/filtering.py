import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping, NamedTuple, Optional, Tuple, Union

import dateutil
import discord.errors
from async_rediscache import RedisCache
from dateutil.relativedelta import relativedelta
from discord import Colour, HTTPException, Member, Message, NotFound, TextChannel
from discord.ext.commands import Cog
from discord.utils import escape_markdown

from bot.api import ResponseCodeError
from bot.bot import Bot
from bot.constants import (
    Channels, Colours, Filter,
    Guild, Icons, URLs
)
from bot.exts.moderation.modlog import ModLog
from bot.utils.messages import format_user
from bot.utils.regex import INVITE_RE
from bot.utils.scheduling import Scheduler

log = logging.getLogger(__name__)

# Regular expressions
CODE_BLOCK_RE = re.compile(
    r"(?P<delim>``?)[^`]+?(?P=delim)(?!`+)"  # Inline codeblock
    r"|```(.+?)```",  # Multiline codeblock
    re.DOTALL | re.MULTILINE
)
EVERYONE_PING_RE = re.compile(rf"@everyone|<@&{Guild.id}>|@here")
SPOILER_RE = re.compile(r"(\|\|.+?\|\|)", re.DOTALL)
URL_RE = re.compile(r"(https?://[^\s]+)", flags=re.IGNORECASE)
ZALGO_RE = re.compile(r"[\u0300-\u036F\u0489]")

# Other constants.
DAYS_BETWEEN_ALERTS = 3
OFFENSIVE_MSG_DELETE_TIME = timedelta(days=Filter.offensive_msg_delete_days)

FilterMatch = Union[re.Match, dict, bool, List[discord.Embed]]


class Stats(NamedTuple):
    """Additional stats on a triggered filter to append to a mod log."""

    message_content: str
    additional_embeds: Optional[List[discord.Embed]]


class Filtering(Cog):
    """Filtering out invites, blacklisting domains, and warning us of certain regular expressions."""

    # Redis cache mapping a user ID to the last timestamp a bad nickname alert was sent
    name_alerts = RedisCache()

    def __init__(self, bot: Bot):
        self.bot = bot
        self.scheduler = Scheduler(self.__class__.__name__)
        self.name_lock = asyncio.Lock()

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
                ),
                "schedule_deletion": False
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
                ),
                "schedule_deletion": False
            },
            "filter_domains": {
                "enabled": Filter.filter_domains,
                "function": self._has_urls,
                "type": "filter",
                "content_only": True,
                "user_notification": Filter.notify_user_domains,
                "notification_msg": (
                    f"Your URL has been removed because it matched a blacklisted domain. {staff_mistake_str}"
                ),
                "schedule_deletion": False
            },
            "filter_everyone_ping": {
                "enabled": Filter.filter_everyone_ping,
                "function": self._has_everyone_ping,
                "type": "filter",
                "content_only": True,
                "user_notification": Filter.notify_user_everyone_ping,
                "notification_msg": (
                    "Please don't try to ping `@everyone` or `@here`. "
                    f"Your message has been removed. {staff_mistake_str}"
                ),
                "schedule_deletion": False,
                "ping_everyone": False
            },
            "watch_regex": {
                "enabled": Filter.watch_regex,
                "function": self._has_watch_regex_match,
                "type": "watchlist",
                "content_only": True,
                "schedule_deletion": True
            },
            "watch_rich_embeds": {
                "enabled": Filter.watch_rich_embeds,
                "function": self._has_rich_embed,
                "type": "watchlist",
                "content_only": False,
                "schedule_deletion": False
            }
        }

        self.bot.loop.create_task(self.reschedule_offensive_msg_deletion())

    def cog_unload(self) -> None:
        """Cancel scheduled tasks."""
        self.scheduler.cancel_all()

    def _get_filterlist_items(self, list_type: str, *, allowed: bool) -> list:
        """Fetch items from the filter_list_cache."""
        return self.bot.filter_list_cache[f"{list_type.upper()}.{allowed}"].keys()

    def _get_filterlist_value(self, list_type: str, value: Any, *, allowed: bool) -> dict:
        """Fetch one specific value from filter_list_cache."""
        return self.bot.filter_list_cache[f"{list_type.upper()}.{allowed}"][value]

    @staticmethod
    def _expand_spoilers(text: str) -> str:
        """Return a string containing all interpretations of a spoilered message."""
        split_text = SPOILER_RE.split(text)
        return ''.join(
            split_text[0::2] + split_text[1::2] + split_text
        )

    @property
    def mod_log(self) -> ModLog:
        """Get currently loaded ModLog cog instance."""
        return self.bot.get_cog("ModLog")

    @Cog.listener()
    async def on_message(self, msg: Message) -> None:
        """Invoke message filter for new messages."""
        await self._filter_message(msg)

        # Ignore webhook messages.
        if msg.webhook_id is None:
            await self.check_bad_words_in_name(msg.author)

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

    def get_name_matches(self, name: str) -> List[re.Match]:
        """Check bad words from passed string (name). Return list of matches."""
        matches = []
        watchlist_patterns = self._get_filterlist_items('filter_token', allowed=False)
        for pattern in watchlist_patterns:
            if match := re.search(pattern, name, flags=re.IGNORECASE):
                matches.append(match)
        return matches

    async def check_send_alert(self, member: Member) -> bool:
        """When there is less than 3 days after last alert, return `False`, otherwise `True`."""
        if last_alert := await self.name_alerts.get(member.id):
            last_alert = datetime.utcfromtimestamp(last_alert)
            if datetime.utcnow() - timedelta(days=DAYS_BETWEEN_ALERTS) < last_alert:
                log.trace(f"Last alert was too recent for {member}'s nickname.")
                return False

        return True

    async def check_bad_words_in_name(self, member: Member) -> None:
        """Send a mod alert every 3 days if a username still matches a watchlist pattern."""
        # Use lock to avoid race conditions
        async with self.name_lock:
            # Check whether the users display name contains any words in our blacklist
            matches = self.get_name_matches(member.display_name)

            if not matches or not await self.check_send_alert(member):
                return

            log.info(f"Sending bad nickname alert for '{member.display_name}' ({member.id}).")

            log_string = (
                f"**User:** {format_user(member)}\n"
                f"**Display Name:** {escape_markdown(member.display_name)}\n"
                f"**Bad Matches:** {', '.join(match.group() for match in matches)}"
            )

            await self.mod_log.send_log_message(
                icon_url=Icons.token_removed,
                colour=Colours.soft_red,
                title="Username filtering alert",
                text=log_string,
                channel_id=Channels.mod_alerts,
                thumbnail=member.avatar_url
            )

            # Update time when alert sent
            await self.name_alerts.set(member.id, datetime.utcnow().timestamp())

    async def filter_eval(self, result: str, msg: Message) -> bool:
        """
        Filter the result of an !eval to see if it violates any of our rules, and then respond accordingly.

        Also requires the original message, to check whether to filter and for mod logs.
        Returns whether a filter was triggered or not.
        """
        filter_triggered = False
        # Should we filter this message?
        if self._check_filter(msg):
            for filter_name, _filter in self.filters.items():
                # Is this specific filter enabled in the config?
                # We also do not need to worry about filters that take the full message,
                # since all we have is an arbitrary string.
                if _filter["enabled"] and _filter["content_only"]:
                    filter_result = await _filter["function"](result)
                    reason = None

                    if isinstance(filter_result, tuple):
                        match, reason = filter_result
                    else:
                        match = filter_result

                    if match:
                        # If this is a filter (not a watchlist), we set the variable so we know
                        # that it has been triggered
                        if _filter["type"] == "filter":
                            filter_triggered = True

                        stats = self._add_stats(filter_name, match, result)
                        await self._send_log(filter_name, _filter, msg, stats, reason, is_eval=True)

                        break  # We don't want multiple filters to trigger

        return filter_triggered

    async def _filter_message(self, msg: Message, delta: Optional[int] = None) -> None:
        """Filter the input message to see if it violates any of our rules, and then respond accordingly."""
        # Should we filter this message?
        if self._check_filter(msg):
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
                        payload = msg.content
                    else:
                        payload = msg

                    result = await _filter["function"](payload)
                    reason = None

                    if isinstance(result, tuple):
                        match, reason = result
                    else:
                        match = result

                    if match:
                        is_private = msg.channel.type is discord.ChannelType.private

                        # If this is a filter (not a watchlist) and not in a DM, delete the message.
                        if _filter["type"] == "filter" and not is_private:
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

                        # If the message is classed as offensive, we store it in the site db and
                        # it will be deleted it after one week.
                        if _filter["schedule_deletion"] and not is_private:
                            delete_date = (msg.created_at + OFFENSIVE_MSG_DELETE_TIME).isoformat()
                            data = {
                                'id': msg.id,
                                'channel_id': msg.channel.id,
                                'delete_date': delete_date
                            }

                            try:
                                await self.bot.api_client.post('bot/offensive-messages', json=data)
                            except ResponseCodeError as e:
                                if e.status == 400 and "already exists" in e.response_json.get("id", [""])[0]:
                                    log.debug(f"Offensive message {msg.id} already exists.")
                                else:
                                    log.error(f"Offensive message {msg.id} failed to post: {e}")
                            else:
                                self.schedule_msg_delete(data)
                                log.trace(f"Offensive message {msg.id} will be deleted on {delete_date}")

                        stats = self._add_stats(filter_name, match, msg.content)
                        await self._send_log(filter_name, _filter, msg, stats, reason)

                        break  # We don't want multiple filters to trigger

    async def _send_log(
        self,
        filter_name: str,
        _filter: Dict[str, Any],
        msg: discord.Message,
        stats: Stats,
        reason: Optional[str] = None,
        *,
        is_eval: bool = False,
    ) -> None:
        """Send a mod log for a triggered filter."""
        if msg.channel.type is discord.ChannelType.private:
            channel_str = "via DM"
            ping_everyone = False
        else:
            channel_str = f"in {msg.channel.mention}"
            # Allow specific filters to override ping_everyone
            ping_everyone = Filter.ping_everyone and _filter.get("ping_everyone", True)

        eval_msg = "using !eval " if is_eval else ""
        footer = f"Reason: {reason}" if reason else None
        message = (
            f"The {filter_name} {_filter['type']} was triggered by {format_user(msg.author)} "
            f"{channel_str} {eval_msg}with [the following message]({msg.jump_url}):\n\n"
            f"{stats.message_content}"
        )

        log.debug(message)

        # Send pretty mod log embed to mod-alerts
        await self.mod_log.send_log_message(
            icon_url=Icons.filtering,
            colour=Colour(Colours.soft_red),
            title=f"{_filter['type'].title()} triggered!",
            text=message,
            thumbnail=msg.author.avatar_url_as(static_format="png"),
            channel_id=Channels.mod_alerts,
            ping_everyone=ping_everyone,
            additional_embeds=stats.additional_embeds,
            footer=footer,
        )

    def _add_stats(self, name: str, match: FilterMatch, content: str) -> Stats:
        """Adds relevant statistical information to the relevant filter and increments the bot's stats."""
        # Word and match stats for watch_regex
        if name == "watch_regex":
            surroundings = match.string[max(match.start() - 10, 0): match.end() + 10]
            message_content = (
                f"**Match:** '{match[0]}'\n"
                f"**Location:** '...{escape_markdown(surroundings)}...'\n"
                f"\n**Original Message:**\n{escape_markdown(content)}"
            )
        else:  # Use original content
            message_content = content

        additional_embeds = None

        self.bot.stats.incr(f"filters.{name}")

        # The function returns True for invalid invites.
        # They have no data so additional embeds can't be created for them.
        if name == "filter_invites" and match is not True:
            additional_embeds = []
            for _, data in match.items():
                reason = f"Reason: {data['reason']} | " if data.get('reason') else ""
                embed = discord.Embed(description=(
                    f"**Members:**\n{data['members']}\n"
                    f"**Active:**\n{data['active']}"
                ))
                embed.set_author(name=data["name"])
                embed.set_thumbnail(url=data["icon"])
                embed.set_footer(text=f"{reason}Guild ID: {data['id']}")
                additional_embeds.append(embed)

        elif name == "watch_rich_embeds":
            additional_embeds = match

        return Stats(message_content, additional_embeds)

    @staticmethod
    def _check_filter(msg: Message) -> bool:
        """Check whitelists to see if we should filter this message."""
        role_whitelisted = False

        if type(msg.author) is Member:  # Only Member has roles, not User.
            for role in msg.author.roles:
                if role.id in Filter.role_whitelist:
                    role_whitelisted = True

        return (
            msg.channel.id not in Filter.channel_whitelist  # Channel not in whitelist
            and not role_whitelisted                        # Role not in whitelist
            and not msg.author.bot                          # Author not a bot
        )

    async def _has_watch_regex_match(self, text: str) -> Tuple[Union[bool, re.Match], Optional[str]]:
        """
        Return True if `text` matches any regex from `word_watchlist` or `token_watchlist` configs.

        `word_watchlist`'s patterns are placed between word boundaries while `token_watchlist` is
        matched as-is. Spoilers are expanded, if any, and URLs are ignored.
        Second return value is a reason written to database about blacklist entry (can be None).
        """
        if SPOILER_RE.search(text):
            text = self._expand_spoilers(text)

        # Make sure it's not a URL
        if URL_RE.search(text):
            return False, None

        watchlist_patterns = self._get_filterlist_items('filter_token', allowed=False)
        for pattern in watchlist_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match, self._get_filterlist_value('filter_token', pattern, allowed=False)['comment']

        return False, None

    async def _has_urls(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        Returns True if the text contains one of the blacklisted URLs from the config file.

        Second return value is a reason of URL blacklisting (can be None).
        """
        if not URL_RE.search(text):
            return False, None

        text = text.lower()
        domain_blacklist = self._get_filterlist_items("domain_name", allowed=False)

        for url in domain_blacklist:
            if url.lower() in text:
                return True, self._get_filterlist_value("domain_name", url, allowed=False)["comment"]

        return False, None

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

            guild_id = guild.get("id")
            guild_invite_whitelist = self._get_filterlist_items("guild_invite", allowed=True)
            guild_invite_blacklist = self._get_filterlist_items("guild_invite", allowed=False)

            # Is this invite allowed?
            guild_partnered_or_verified = (
                'PARTNERED' in guild.get("features", [])
                or 'VERIFIED' in guild.get("features", [])
            )
            invite_not_allowed = (
                guild_id in guild_invite_blacklist           # Blacklisted guilds are never permitted.
                or guild_id not in guild_invite_whitelist    # Whitelisted guilds are always permitted.
                and not guild_partnered_or_verified          # Otherwise guilds have to be Verified or Partnered.
            )

            if invite_not_allowed:
                reason = None
                if guild_id in guild_invite_blacklist:
                    reason = self._get_filterlist_value("guild_invite", guild_id, allowed=False)["comment"]

                guild_icon_hash = guild["icon"]
                guild_icon = (
                    "https://cdn.discordapp.com/icons/"
                    f"{guild_id}/{guild_icon_hash}.png?size=512"
                )

                invite_data[invite] = {
                    "name": guild["name"],
                    "id": guild['id'],
                    "icon": guild_icon,
                    "members": response["approximate_member_count"],
                    "active": response["approximate_presence_count"],
                    "reason": reason
                }

        return invite_data if invite_data else False

    @staticmethod
    async def _has_rich_embed(msg: Message) -> Union[bool, List[discord.Embed]]:
        """Determines if `msg` contains any rich embeds not auto-generated from a URL."""
        if msg.embeds:
            for embed in msg.embeds:
                if embed.type == "rich":
                    urls = URL_RE.findall(msg.content)
                    if not embed.url or embed.url not in urls:
                        # If `embed.url` does not exist or if `embed.url` is not part of the content
                        # of the message, it's unlikely to be an auto-generated embed by Discord.
                        return msg.embeds
                    else:
                        log.trace(
                            "Found a rich embed sent by a regular user account, "
                            "but it was likely just an automatic URL embed."
                        )
                        return False
        return False

    @staticmethod
    async def _has_everyone_ping(text: str) -> bool:
        """Determines if `msg` contains an @everyone or @here ping outside of a codeblock."""
        # First pass to avoid running re.sub on every message
        if not EVERYONE_PING_RE.search(text):
            return False

        content_without_codeblocks = CODE_BLOCK_RE.sub("", text)
        return bool(EVERYONE_PING_RE.search(content_without_codeblocks))

    async def notify_member(self, filtered_member: Member, reason: str, channel: TextChannel) -> None:
        """
        Notify filtered_member about a moderation action with the reason str.

        First attempts to DM the user, fall back to in-channel notification if user has DMs disabled
        """
        try:
            await filtered_member.send(reason)
        except discord.errors.Forbidden:
            await channel.send(f"{filtered_member.mention} {reason}")

    def schedule_msg_delete(self, msg: dict) -> None:
        """Delete an offensive message once its deletion date is reached."""
        delete_at = dateutil.parser.isoparse(msg['delete_date']).replace(tzinfo=None)
        self.scheduler.schedule_at(delete_at, msg['id'], self.delete_offensive_msg(msg))

    async def reschedule_offensive_msg_deletion(self) -> None:
        """Get all the pending message deletion from the API and reschedule them."""
        await self.bot.wait_until_ready()
        response = await self.bot.api_client.get('bot/offensive-messages',)

        now = datetime.utcnow()

        for msg in response:
            delete_at = dateutil.parser.isoparse(msg['delete_date']).replace(tzinfo=None)

            if delete_at < now:
                await self.delete_offensive_msg(msg)
            else:
                self.schedule_msg_delete(msg)

    async def delete_offensive_msg(self, msg: Mapping[str, str]) -> None:
        """Delete an offensive message, and then delete it from the db."""
        try:
            channel = self.bot.get_channel(msg['channel_id'])
            if channel:
                msg_obj = await channel.fetch_message(msg['id'])
                await msg_obj.delete()
        except NotFound:
            log.info(
                f"Tried to delete message {msg['id']}, but the message can't be found "
                f"(it has been probably already deleted)."
            )
        except HTTPException as e:
            log.warning(f"Failed to delete message {msg['id']}: status {e.status}")

        await self.bot.api_client.delete(f'bot/offensive-messages/{msg["id"]}')
        log.info(f"Deleted the offensive message with id {msg['id']}.")


def setup(bot: Bot) -> None:
    """Load the Filtering cog."""
    bot.add_cog(Filtering(bot))
