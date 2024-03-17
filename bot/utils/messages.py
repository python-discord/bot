import random
import re
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from functools import partial
from io import BytesIO
from itertools import zip_longest

import discord
from discord import Message
from discord.ext.commands import Context
from pydis_core.site_api import ResponseCodeError
from pydis_core.utils import scheduling
from sentry_sdk import add_breadcrumb

import bot
from bot.constants import Emojis, MODERATION_ROLES, NEGATIVE_REPLIES, URLs
from bot.log import get_logger

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

    log.trace(f"Removing reaction {reaction} by {user} on {reaction.message.id}: disallowed user.")
    scheduling.create_task(
        reaction.message.remove_reaction(reaction.emoji, user),
        suppressed_exceptions=(discord.HTTPException,),
        name=f"remove_reaction-{reaction}-{reaction.message.id}-{user}"
    )
    return False


async def wait_for_deletion(
    message: discord.Message | discord.InteractionMessage,
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
            await bot.instance.wait_for("reaction_add", check=check, timeout=timeout)
        except TimeoutError:
            await message.clear_reactions()
        else:
            await message.delete()

    except discord.NotFound:
        log.trace(f"wait_for_deletion: message {message.id} deleted prematurely.")

    except discord.HTTPException:
        if not isinstance(message.channel, discord.Thread):
            # Threads might not be accessible by the time the timeout expires
            raise


async def send_attachments(
    message: discord.Message,
    destination: discord.TextChannel | discord.Webhook,
    link_large: bool = True,
    use_cached: bool = False,
    **kwargs
) -> list[str]:
    """
    Re-upload the message's attachments to the destination and return a list of their new URLs.

    Each attachment is sent as a separate message to more easily comply with the request/file size
    limit. If link_large is True, attachments which are too large are instead grouped into a single
    embed which links to them. Extra kwargs will be passed to send() when sending the attachment.
    """
    webhook_send_kwargs = {
        "username": message.author.display_name,
        "avatar_url": message.author.display_avatar.url,
    }
    webhook_send_kwargs.update(kwargs)
    webhook_send_kwargs["username"] = sub_clyde(webhook_send_kwargs["username"])

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


def sub_clyde(username: str | None) -> str | None:
    """
    Replace "e"/"E" in any "clyde" in `username` with a Cyrillic "е"/"Е" and return the new string.

    Discord disallows "clyde" anywhere in the username for webhooks. It will return a 400.
    Return None only if `username` is None.
    """  # noqa: RUF002
    def replace_e(match: re.Match) -> str:
        char = "е" if match[2] == "e" else "Е"  # noqa: RUF001
        return match[1] + char

    if username:
        return re.sub(r"(clyd)(e)", replace_e, username, flags=re.I)
    return username  # Empty string or None


async def send_denial(ctx: Context, reason: str) -> discord.Message:
    """Send an embed denying the user with the given reason."""
    embed = discord.Embed()
    embed.colour = discord.Colour.red()
    embed.title = random.choice(NEGATIVE_REPLIES)
    embed.description = reason

    return await ctx.send(embed=embed)


def format_user(user: discord.User | discord.Member) -> str:
    """Return a string for `user` which has their mention and ID."""
    return f"{user.mention} (`{user.id}`)"


def format_channel(channel: discord.abc.Messageable) -> str:
    """Return a string for `channel` with its mention, ID, and the parent channel if it is a thread."""
    formatted = f"{channel.mention} ({channel.category}/#{channel}"
    if hasattr(channel, "parent"):
        formatted += f"/{channel.parent}"
    formatted += ")"
    return formatted


async def upload_log(
    messages: Iterable[Message],
    actor_id: int,
    attachments: dict[int, list[str]] | None = None,
) -> str:
    """Upload message logs to the database and return a URL to a page for viewing the logs."""
    if attachments is None:
        attachments = []
    else:
        attachments = [attachments.get(message.id, []) for message in messages]

    deletedmessage_set = [
        {
            "id": message.id,
            "author": message.author.id,
            "channel_id": message.channel.id,
            "content": message.content.replace("\0", ""),  # Null chars cause 400.
            "embeds": [embed.to_dict() for embed in message.embeds],
            "attachments": attachment,
        }
        for message, attachment in zip_longest(messages, attachments, fillvalue=[])
    ]

    try:
        response = await bot.instance.api_client.post(
            "bot/deleted-messages",
            json={
                "actor": actor_id,
                "creation": datetime.now(UTC).isoformat(),
                "deletedmessage_set": deletedmessage_set,
            }
        )
    except ResponseCodeError as e:
        add_breadcrumb(
            category="api_error",
            message=str(e),
            level="error",
            data=deletedmessage_set,
        )
        raise

    return f"{URLs.site_logs_view}/{response['id']}"
