from operator import attrgetter

import discord

import bot
from bot import constants
from bot.exts.help_channels import _caches
from bot.log import get_logger
from bot.utils import lock

log = get_logger(__name__)
NAMESPACE = "help"


def _serialise_session_participants(participants: set[int]) -> str:
    """Convert a set to a comma separated string."""
    return ",".join(str(p) for p in participants)


def _deserialise_session_participants(s: str) -> set[int]:
    """Convert a comma separated string into a set."""
    return set(int(user_id) for user_id in s.split(",") if user_id != "")


@lock.lock_arg(NAMESPACE, "message", attrgetter("channel.id"))
@lock.lock_arg(NAMESPACE, "message", attrgetter("author.id"))
async def notify_session_participants(message: discord.Message) -> None:
    """
    Check if the message author meets the requirements to be notified.

    If they meet the requirements they are notified.
    """
    if message.channel.owner_id == message.author.id:
        return  # Ignore messages sent by claimants

    if not await _caches.help_dm.get(message.author.id):
        return  # Ignore message if user is opted out of help dms

    session_participants = _deserialise_session_participants(
        await _caches.session_participants.get(message.channel.id) or "",
    )

    if message.author.id not in session_participants:
        session_participants.add(message.author.id)

        embed = discord.Embed(
            title="Currently Helping",
            description=f"You're currently helping in {message.channel.mention}",
            color=constants.Colours.bright_green,
            timestamp=message.created_at,
        )
        embed.add_field(name="Conversation", value=f"[Jump to message]({message.jump_url})")

        try:
            await message.author.send(embed=embed)
        except discord.Forbidden:
            log.trace(
                f"Failed to send help dm message to {message.author.id}. DMs Closed/Blocked. "
                "Removing user from help dm."
            )
            await _caches.help_dm.delete(message.author.id)
            bot_commands_channel = bot.instance.get_channel(constants.Channels.bot_commands)
            await bot_commands_channel.send(
                f"{message.author.mention} {constants.Emojis.cross_mark} "
                "To receive updates on help channels you're active in, enable your DMs.",
                delete_after=constants.RedirectOutput.delete_delay,
            )
            return

        await _caches.session_participants.set(
            message.channel.id,
            _serialise_session_participants(session_participants),
        )
