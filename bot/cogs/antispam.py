import asyncio
import logging
import textwrap
from datetime import datetime, timedelta
from typing import List

from dateutil.relativedelta import relativedelta
from discord import Colour, Member, Message, Object, TextChannel
from discord.ext.commands import Bot

from bot import rules
from bot.cogs.modlog import ModLog
from bot.constants import (
    AntiSpam as AntiSpamConfig, Channels,
    Colours, DEBUG_MODE, Event,
    Guild as GuildConfig, Icons, Roles,
)
from bot.utils.time import humanize_delta


log = logging.getLogger(__name__)

RULE_FUNCTION_MAPPING = {
    'attachments': rules.apply_attachments,
    'burst': rules.apply_burst,
    'burst_shared': rules.apply_burst_shared,
    'chars': rules.apply_chars,
    'discord_emojis': rules.apply_discord_emojis,
    'duplicates': rules.apply_duplicates,
    'links': rules.apply_links,
    'mentions': rules.apply_mentions,
    'newlines': rules.apply_newlines,
    'role_mentions': rules.apply_role_mentions
}
WHITELISTED_CHANNELS = (
    Channels.admins, Channels.announcements, Channels.big_brother_logs,
    Channels.devalerts, Channels.devlog, Channels.devtest,
    Channels.helpers, Channels.message_log,
    Channels.mod_alerts, Channels.modlog, Channels.staff_lounge
)
WHITELISTED_ROLES = (Roles.owner, Roles.admin, Roles.moderator, Roles.helpers)


class AntiSpam:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.muted_role = None

    @property
    def mod_log(self) -> ModLog:
        return self.bot.get_cog("ModLog")

    async def on_ready(self):
        role_id = AntiSpamConfig.punishment['role_id']
        self.muted_role = Object(role_id)

    async def on_message(self, message: Message):
        if (
            not message.guild
            or message.guild.id != GuildConfig.id
            or message.author.bot
            or (message.channel.id in WHITELISTED_CHANNELS and not DEBUG_MODE)
            or (message.author.top_role.id in WHITELISTED_ROLES and not DEBUG_MODE)
        ):
            return

        # Fetch the rule configuration with the highest rule interval.
        max_interval_config = max(
            AntiSpamConfig.rules.values(),
            key=lambda config: config['interval']
        )
        max_interval = max_interval_config['interval']

        # Store history messages since `interval` seconds ago in a list to prevent unnecessary API calls.
        earliest_relevant_at = datetime.utcnow() - timedelta(seconds=max_interval)
        relevant_messages = [
            msg async for msg in message.channel.history(after=earliest_relevant_at, reverse=False)
        ]

        for rule_name in AntiSpamConfig.rules:
            rule_config = AntiSpamConfig.rules[rule_name]
            rule_function = RULE_FUNCTION_MAPPING[rule_name]

            # Create a list of messages that were sent in the interval that the rule cares about.
            latest_interesting_stamp = datetime.utcnow() - timedelta(seconds=rule_config['interval'])
            messages_for_rule = [
                msg for msg in relevant_messages if msg.created_at > latest_interesting_stamp
            ]
            result = await rule_function(message, messages_for_rule, rule_config)

            # If the rule returns `None`, that means the message didn't violate it.
            # If it doesn't, it returns a tuple in the form `(str, Iterable[discord.Member])`
            # which contains the reason for why the message violated the rule and
            # an iterable of all members that violated the rule.
            if result is not None:
                reason, members, relevant_messages = result
                full_reason = f"`{rule_name}` rule: {reason}"
                for member in members:

                    # Fire it off as a background task to ensure
                    # that the sleep doesn't block further tasks
                    self.bot.loop.create_task(
                        self.punish(message, member, full_reason, relevant_messages)
                    )

                await self.maybe_delete_messages(message.channel, relevant_messages)
                break

    async def punish(self, msg: Message, member: Member, reason: str, messages: List[Message]):
        # Sanity check to ensure we're not lagging behind
        if self.muted_role not in member.roles:
            remove_role_after = AntiSpamConfig.punishment['remove_after']
            duration_delta = relativedelta(seconds=remove_role_after)
            human_duration = humanize_delta(duration_delta)

            mod_alert_message = (
                f"**Triggered by:** {member.display_name}#{member.discriminator} (`{member.id}`)\n"
                f"**Channel:** {msg.channel.mention}\n"
                f"**Reason:** {reason}\n"
            )

            # For multiple messages, use the logs API
            if len(messages) > 1:
                url = await self.mod_log.upload_log(messages)
                mod_alert_message += f"A complete log of the offending messages can be found [here]({url})"
            else:
                mod_alert_message += "Message:\n"
                content = messages[0].clean_content
                remaining_chars = 2040 - len(mod_alert_message)

                if len(content) > remaining_chars:
                    content = content[:remaining_chars] + "..."

                mod_alert_message += f"{content}"

            await self.mod_log.send_log_message(
                icon_url=Icons.filtering,
                colour=Colour(Colours.soft_red),
                title=f"Spam detected!",
                text=mod_alert_message,
                thumbnail=msg.author.avatar_url_as(static_format="png"),
                channel_id=Channels.mod_alerts,
                ping_everyone=AntiSpamConfig.ping_everyone
            )

            await member.add_roles(self.muted_role, reason=reason)
            description = textwrap.dedent(f"""
                **Channel**: {msg.channel.mention}
                **User**: {msg.author.mention} (`{msg.author.id}`)
                **Reason**: {reason}
                Role will be removed after {human_duration}.
            """)

            await self.mod_log.send_log_message(
                icon_url=Icons.user_mute, colour=Colour(Colours.soft_red),
                title="User muted", text=description
            )

            await asyncio.sleep(remove_role_after)
            await member.remove_roles(self.muted_role, reason="AntiSpam mute expired")

            await self.mod_log.send_log_message(
                icon_url=Icons.user_mute, colour=Colour(Colours.soft_green),
                title="User unmuted",
                text=f"Was muted by `AntiSpam` cog for {human_duration}."
            )

    async def maybe_delete_messages(self, channel: TextChannel, messages: List[Message]):
        # Is deletion of offending messages actually enabled?
        if AntiSpamConfig.clean_offending:

            # If we have more than one message, we can use bulk delete.
            if len(messages) > 1:
                message_ids = [message.id for message in messages]
                self.mod_log.ignore(Event.message_delete, *message_ids)
                await channel.delete_messages(messages)

            # Otherwise, the bulk delete endpoint will throw up.
            # Delete the message directly instead.
            else:
                self.mod_log.ignore(Event.message_delete, messages[0].id)
                await messages[0].delete()


def validate_config():
    for name, config in AntiSpamConfig.rules.items():
        if name not in RULE_FUNCTION_MAPPING:
            raise ValueError(
                f"Unrecognized antispam rule `{name}`. "
                f"Valid rules are: {', '.join(RULE_FUNCTION_MAPPING)}"
            )

        for required_key in ('interval', 'max'):
            if required_key not in config:
                raise ValueError(
                    f"`{required_key}` is required but was not "
                    f"set in rule `{name}`'s configuration."
                )


def setup(bot: Bot):
    validate_config()
    bot.add_cog(AntiSpam(bot))
    log.info("Cog loaded: AntiSpam")
