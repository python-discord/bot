import logging
from typing import Optional

import discord
from async_rediscache import RedisCache
from discord import Color
from discord.ext import commands
from discord.ext.commands import Cog

from bot import constants
from bot.bot import Bot
from bot.converters import UserMentionOrID
from bot.utils.checks import in_whitelist_check
from bot.utils.messages import send_attachments
from bot.utils.webhooks import send_webhook

log = logging.getLogger(__name__)


class DMRelay(Cog):
    """Relay direct messages to and from the bot."""

    # RedisCache[str, t.Union[discord.User.id, discord.Member.id]]
    dm_cache = RedisCache()

    def __init__(self, bot: Bot):
        self.bot = bot
        self.webhook_id = constants.Webhooks.dm_log
        self.webhook = None
        self.bot.loop.create_task(self.fetch_webhook())

    @commands.command(aliases=("reply",))
    async def send_dm(self, ctx: commands.Context, member: Optional[UserMentionOrID], *, message: str) -> None:
        """
        Allows you to send a DM to a user from the bot.

        If `member` is not provided, it will send to the last user who DM'd the bot.

        This feature should be used extremely sparingly. Use ModMail if you need to have a serious
        conversation with a user. This is just for responding to extraordinary DMs, having a little
        fun with users, and telling people they are DMing the wrong bot.

        NOTE: This feature will be removed if it is overused.
        """
        if not member:
            user_id = await self.dm_cache.get("last_user")
            member = ctx.guild.get_member(user_id) if user_id else None

        # If we still don't have a Member at this point, give up
        if not member:
            log.debug("This bot has never gotten a DM, or the RedisCache has been cleared.")
            await ctx.message.add_reaction("❌")
            return

        if member.id == self.bot.user.id:
            log.debug("Not sending message to bot user")
            return await ctx.send("🚫 I can't send messages to myself!")

        try:
            await member.send(message)
        except discord.errors.Forbidden:
            log.debug("User has disabled DMs.")
            await ctx.message.add_reaction("❌")
        else:
            await ctx.message.add_reaction("✅")
            self.bot.stats.incr("dm_relay.dm_sent")

    async def fetch_webhook(self) -> None:
        """Fetches the webhook object, so we can post to it."""
        await self.bot.wait_until_guild_available()

        try:
            self.webhook = await self.bot.fetch_webhook(self.webhook_id)
        except discord.HTTPException:
            log.exception(f"Failed to fetch webhook with id `{self.webhook_id}`")

    @Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Relays the message's content and attachments to the dm_log channel."""
        # Only relay DMs from humans
        if message.author.bot or message.guild or self.webhook is None:
            return

        if message.clean_content:
            await send_webhook(
                webhook=self.webhook,
                content=message.clean_content,
                username=f"{message.author.display_name} ({message.author.id})",
                avatar_url=message.author.avatar_url
            )
            await self.dm_cache.set("last_user", message.author.id)
            self.bot.stats.incr("dm_relay.dm_received")

        # Handle any attachments
        if message.attachments:
            try:
                await send_attachments(
                    message,
                    self.webhook,
                    username=f"{message.author.display_name} ({message.author.id})"
                )
            except (discord.errors.Forbidden, discord.errors.NotFound):
                e = discord.Embed(
                    description=":x: **This message contained an attachment, but it could not be retrieved**",
                    color=Color.red()
                )
                await send_webhook(
                    webhook=self.webhook,
                    embed=e,
                    username=f"{message.author.display_name} ({message.author.id})",
                    avatar_url=message.author.avatar_url
                )
            except discord.HTTPException:
                log.exception("Failed to send an attachment to the webhook")

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Only allow moderators to invoke the commands in this cog."""
        checks = [
            await commands.has_any_role(*constants.MODERATION_ROLES).predicate(ctx),
            in_whitelist_check(
                ctx,
                channels=[constants.Channels.dm_log],
                redirect=None,
                fail_silently=True,
            )
        ]
        return all(checks)


def setup(bot: Bot) -> None:
    """Load the DMRelay  cog."""
    bot.add_cog(DMRelay(bot))
