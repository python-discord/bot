import asyncio
import random
import re
from functools import partial
from io import BytesIO
from typing import Callable, List, Optional, Sequence, Union

import discord
from discord.ext.commands import Context, MessageConverter, MessageNotFound

import bot
from bot.constants import Channels, Emojis, MODERATION_ROLES, NEGATIVE_REPLIES, Roles
from bot.log import get_logger
from bot.utils import scheduling
from bot.utils.regex import DISCORD_MESSAGE_LINK_RE

log = get_logger(__name__)


def reaction_check(
    reaction: discord.Reaction,
    user: discord.abc.User,
    *,
    message_id: int,
    allowed_emoji: Sequence[str],
    allowed_users: Sequence[int],
    allow_mods: bool = True,
) -> bool:
    """
    Check if a reaction's emoji and author are allowed and the message is `message_id`.

    If the user is not allowed, remove the reaction. Ignore reactions made by the bot.
    If `allow_mods` is True, allow users with moderator roles even if they're not in `allowed_users`.
    """
    right_reaction = (
        user != bot.instance.user
        and reaction.message.id == message_id
        and str(reaction.emoji) in allowed_emoji
    )
    if not right_reaction:
        return False

    is_moderator = (
        allow_mods
        and any(role.id in MODERATION_ROLES for role in getattr(user, "roles", []))
    )

    if user.id in allowed_users or is_moderator:
        log.trace(f"Allowed reaction {reaction} by {user} on {reaction.message.id}.")
        return True
    else:
        log.trace(f"Removing reaction {reaction} by {user} on {reaction.message.id}: disallowed user.")
        scheduling.create_task(
            reaction.message.remove_reaction(reaction.emoji, user),
            suppressed_exceptions=(discord.HTTPException,),
            name=f"remove_reaction-{reaction}-{reaction.message.id}-{user}"
        )
        return False


async def wait_for_deletion(
    message: discord.Message,
    user_ids: Sequence[int],
    deletion_emojis: Sequence[str] = (Emojis.trashcan,),
    timeout: float = 60 * 5,
    attach_emojis: bool = True,
    allow_mods: bool = True
) -> None:
    """
    Wait for any of `user_ids` to react with one of the `deletion_emojis` within `timeout` seconds to delete `message`.

    If `timeout` expires then reactions are cleared to indicate the option to delete has expired.

    An `attach_emojis` bool may be specified to determine whether to attach the given
    `deletion_emojis` to the message in the given `context`.
    An `allow_mods` bool may also be specified to allow anyone with a role in `MODERATION_ROLES` to delete
    the message.
    """
    if message.guild is None:
        raise ValueError("Message must be sent on a guild")

    if attach_emojis:
        for emoji in deletion_emojis:
            try:
                await message.add_reaction(emoji)
            except discord.NotFound:
                log.trace(f"Aborting wait_for_deletion: message {message.id} deleted prematurely.")
                return

    check = partial(
        reaction_check,
        message_id=message.id,
        allowed_emoji=deletion_emojis,
        allowed_users=user_ids,
        allow_mods=allow_mods,
    )

    try:
        try:
            await bot.instance.wait_for('reaction_add', check=check, timeout=timeout)
        except asyncio.TimeoutError:
            await message.clear_reactions()
        else:
            await message.delete()
    except discord.NotFound:
        log.trace(f"wait_for_deletion: message {message.id} deleted prematurely.")


async def send_attachments(
    message: discord.Message,
    destination: Union[discord.TextChannel, discord.Webhook],
    link_large: bool = True,
    use_cached: bool = False,
    **kwargs
) -> List[str]:
    """
    Re-upload the message's attachments to the destination and return a list of their new URLs.

    Each attachment is sent as a separate message to more easily comply with the request/file size
    limit. If link_large is True, attachments which are too large are instead grouped into a single
    embed which links to them. Extra kwargs will be passed to send() when sending the attachment.
    """
    webhook_send_kwargs = {
        'username': message.author.display_name,
        'avatar_url': message.author.display_avatar.url,
    }
    webhook_send_kwargs.update(kwargs)
    webhook_send_kwargs['username'] = sub_clyde(webhook_send_kwargs['username'])

    large = []
    urls = []
    for attachment in message.attachments:
        failure_msg = (
            f"Failed to re-upload attachment {attachment.filename} from message {message.id}"
        )

        try:
            # Allow 512 bytes of leeway for the rest of the request.
            # This should avoid most files that are too large,
            # but some may get through hence the try-catch.
            if attachment.size <= destination.guild.filesize_limit - 512:
                with BytesIO() as file:
                    await attachment.save(file, use_cached=use_cached)
                    attachment_file = discord.File(file, filename=attachment.filename)

                    if isinstance(destination, discord.TextChannel):
                        msg = await destination.send(file=attachment_file, **kwargs)
                        urls.append(msg.attachments[0].url)
                    else:
                        await destination.send(file=attachment_file, **webhook_send_kwargs)
            elif link_large:
                large.append(attachment)
            else:
                log.info(f"{failure_msg} because it's too large.")
        except discord.HTTPException as e:
            if link_large and e.status == 413:
                large.append(attachment)
            else:
                log.warning(f"{failure_msg} with status {e.status}.", exc_info=e)

    if link_large and large:
        desc = "\n".join(f"[{attachment.filename}]({attachment.url})" for attachment in large)
        embed = discord.Embed(description=desc)
        embed.set_footer(text="Attachments exceed upload size limit.")

        if isinstance(destination, discord.TextChannel):
            await destination.send(embed=embed, **kwargs)
        else:
            await destination.send(embed=embed, **webhook_send_kwargs)

    return urls


async def count_unique_users_reaction(
    message: discord.Message,
    reaction_predicate: Callable[[discord.Reaction], bool] = lambda _: True,
    user_predicate: Callable[[discord.User], bool] = lambda _: True,
    count_bots: bool = True
) -> int:
    """
    Count the amount of unique users who reacted to the message.

    A reaction_predicate function can be passed to check if this reaction should be counted,
    another user_predicate to check if the user should also be counted along with a count_bot flag.
    """
    unique_users = set()

    for reaction in message.reactions:
        if reaction_predicate(reaction):
            async for user in reaction.users():
                if (count_bots or not user.bot) and user_predicate(user):
                    unique_users.add(user.id)

    return len(unique_users)


async def pin_no_system_message(message: discord.Message) -> bool:
    """Pin the given message, wait a couple of seconds and try to delete the system message."""
    await message.pin()

    # Make sure that we give it enough time to deliver the message
    await asyncio.sleep(2)
    # Search for the system message in the last 10 messages
    async for historical_message in message.channel.history(limit=10):
        if historical_message.type == discord.MessageType.pins_add:
            await historical_message.delete()
            return True

    return False


def sub_clyde(username: Optional[str]) -> Optional[str]:
    """
    Replace "e"/"E" in any "clyde" in `username` with a Cyrillic "е"/"E" and return the new string.

    Discord disallows "clyde" anywhere in the username for webhooks. It will return a 400.
    Return None only if `username` is None.
    """
    def replace_e(match: re.Match) -> str:
        char = "е" if match[2] == "e" else "Е"
        return match[1] + char

    if username:
        return re.sub(r"(clyd)(e)", replace_e, username, flags=re.I)
    else:
        return username  # Empty string or None


async def send_denial(ctx: Context, reason: str) -> discord.Message:
    """Send an embed denying the user with the given reason."""
    embed = discord.Embed()
    embed.colour = discord.Colour.red()
    embed.title = random.choice(NEGATIVE_REPLIES)
    embed.description = reason

    return await ctx.send(embed=embed)


def format_user(user: discord.abc.User) -> str:
    """Return a string for `user` which has their mention and ID."""
    return f"{user.mention} (`{user.id}`)"


def shorten_text(text: str) -> str:
    """
    Truncate the text if there are over 3 lines or 300 characters, or if it is a single word.

    The maximum length of the string would be 303 characters across 3 lines at maximum.
    """
    original_length = len(text)
    # Truncate text to a maximum of 300 characters
    if len(text) > 300:
        text = text[:300]

    # Limit to a maximum of three lines
    text = "\n".join(text.split("\n", maxsplit=3)[:3])

    # If it is a single word, then truncate it to 50 characters
    if text.find(" ") == -1:
        text = text[:50]

    # Remove extra whitespaces from the `text`
    text = text.strip()

    # Add placeholder if the text was shortened
    if len(text) < original_length:
        text = f"{text}..."

    return text


async def extract_message_links(message: discord.Message) -> Optional[list[str]]:
    """This method extracts discord message links from a message object."""
    return [msg_link[0] for msg_link in DISCORD_MESSAGE_LINK_RE.findall(message.content)]


async def make_message_link_embed(ctx: Context, message_link: str) -> Optional[discord.Embed]:
    """Create an embedded representation of the discord message link."""
    embed = None

    try:
        message: discord.Message = await MessageConverter().convert(ctx, message_link)
    except MessageNotFound:
        mod_logs_channel = ctx.bot.get_channel(Channels.mod_log)
        last_100_logs: list[discord.Message] = await mod_logs_channel.history(limit=100).flatten()

        for log_entry in last_100_logs:
            if not log_entry.embeds:
                continue

            log_embed: discord.Embed = log_entry.embeds[0]
            if (
                log_embed.author.name == "Message deleted"
                and f"[Jump to message]({message_link})" in log_embed.description
            ):
                embed = discord.Embed(
                    colour=discord.Colour.dark_gold(),
                    title="Deleted Message Link",
                    description=(
                        f"Found <#{Channels.mod_log}> entry for deleted message: "
                        f"[Jump to message]({log_entry.jump_url})."
                    )
                )
        if not embed:
            embed = discord.Embed(
                colour=discord.Colour.red(),
                title="Bad Message Link",
                description=f"Message {message_link} not found."
            )
    except discord.DiscordException as e:
        log.exception(f"Failed to make message link embed for '{message_link}', raised exception: {e}")
    else:
        channel = message.channel
        if not channel.permissions_for(channel.guild.get_role(Roles.helpers)).view_channel:
            log.info(
                f"Helpers don't have read permissions in #{channel.name},"
                f" not sending message link embed for {message_link}"
            )
            return

        embed = discord.Embed(
            colour=discord.Colour.gold(),
            description=(
                f"**Author:** {format_user(message.author)}\n"
                f"**Channel:** {channel.mention} ({channel.category}"
                f"{f'/#{channel.parent.name} - ' if isinstance(channel, discord.Thread) else '/#'}"
                f"{channel.name})\n"
            ),
            timestamp=message.created_at
        )
        embed.add_field(
            name="Content",
            value=shorten_text(message.content) if message.content else "[No Message Content]"
        )
        embed.set_footer(text=f"Message ID: {message.id}")

        if message.attachments:
            embed.set_image(url=message.attachments[0].url)

    return embed
