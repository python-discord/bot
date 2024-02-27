from datetime import UTC, datetime

import discord

from bot.bot import Bot
from bot.constants import Channels, Roles


async def send_log_message(
    bot: Bot,
    icon_url: str | None,
    colour: discord.Colour | int,
    title: str | None,
    text: str,
    *,
    thumbnail: str | discord.Asset | None = None,
    channel_id: int = Channels.mod_log,
    ping_everyone: bool = False,
    files: list[discord.File] | None = None,
    content: str | None = None,
    additional_embeds: list[discord.Embed] | None = None,
    timestamp_override: datetime | None = None,
    footer: str | None = None,
) -> discord.Message:
    """Generate log embed and send to logging channel."""
    await bot.wait_until_guild_available()
    # Truncate string directly here to avoid removing newlines
    embed = discord.Embed(
        description=text[:4093] + "..." if len(text) > 4096 else text
    )

    if title and icon_url:
        embed.set_author(name=title, icon_url=icon_url)
    elif title:
        raise ValueError("title cannot be set without icon_url")
    elif icon_url:
        raise ValueError("icon_url cannot be set without title")

    embed.colour = colour
    embed.timestamp = timestamp_override or datetime.now(tz=UTC)

    if footer:
        embed.set_footer(text=footer)

    if thumbnail:
        embed.set_thumbnail(url=thumbnail)

    if ping_everyone:
        if content:
            content = f"<@&{Roles.moderators}> {content}"
        else:
            content = f"<@&{Roles.moderators}>"

    # Truncate content to 2000 characters and append an ellipsis.
    if content and len(content) > 2000:
        content = content[:2000 - 3] + "..."

    channel = bot.get_channel(channel_id)
    log_message = await channel.send(
        content=content,
        embed=embed,
        files=files
    )

    if additional_embeds:
        for additional_embed in additional_embeds:
            await channel.send(embed=additional_embed)

    return log_message
