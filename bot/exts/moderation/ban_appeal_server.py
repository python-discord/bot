import asyncio
import weakref
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands
from pydis_core.utils import members, scheduling
from pydis_core.utils.channel import get_or_fetch_channel

from bot.bot import Bot
from bot.constants import Channels, Colours, Guild, Roles, URLs
from bot.log import get_logger

log = get_logger(__name__)


PYDIS_NO_KICK_ROLE_IDS = (Roles.admins, Roles.devops)
# A Kubernetes service account token for the Polonium API, mounted by the bot's deployment.
POLONIUM_TOKEN_FILE = Path("/var/run/secrets/polonium-api/token")


class BanAppeals(commands.Cog):
    """Keep the ban appeal server to banned users only, and post their joins and leaves in their modmail thread."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.user_locks: weakref.WeakValueDictionary[int, asyncio.Lock] = weakref.WeakValueDictionary()
        # Users we kicked ourselves, so the leave that follows isn't also posted as them leaving.
        self.ignore_next_remove_event: set[int] = set()

    async def cog_load(self) -> None:
        """Look up the guilds and log channel, then kick anyone who shouldn't be in the appeals server."""
        self.appeals_guild = self.bot.get_guild(Guild.ban_appeal_id)
        self.pydis_guild = self.bot.get_guild(Guild.id)
        self.logs_channel = self.bot.get_channel(Channels.ban_appeal_logs)
        scheduling.create_task(self._sync_kicks())

    async def _sync_kicks(self) -> None:
        """Kick every member of the appeals server who shouldn't be there."""
        await self.bot.wait_until_ready()
        log.info("Starting kick job for ban appeals server")
        for member in self.appeals_guild.members:
            await self._maybe_kick_user(member)
        log.info("Kick job for ban appeals server completed")

    async def _is_banned_pydis(self, member: discord.Member) -> bool:
        """See if the given member is banned in PyDis."""
        try:
            await self.pydis_guild.fetch_ban(member)
        except discord.NotFound:
            return False
        return True

    async def _can_bypass_kick(self, member: discord.Member) -> bool:
        """See if the given appeals server member is staff who may stay without being banned."""
        pydis_member = await members.get_or_fetch_member(self.pydis_guild, member.id)
        if not pydis_member:
            return False
        return (
            any(role.id in PYDIS_NO_KICK_ROLE_IDS for role in pydis_member.roles)
            or any(role.id == Roles.ban_appeal_server_staff for role in member.roles)
        )

    async def _get_thread(self, user: discord.abc.Snowflake) -> discord.Thread | None:
        """Return the user's currently open modmail thread, if they have one."""
        try:
            # Read on every call, as Kubernetes rotates this token every few minutes.
            token = POLONIUM_TOKEN_FILE.read_text().strip()
            async with self.bot.http_session.get(
                f"{URLs.polonium_api}/users/{user.id}/current-post",
                headers={"Authorization": f"Bearer {token}"},
            ) as resp:
                if resp.status == 404:
                    return None
                resp.raise_for_status()
                post = await resp.json()
                if post["guild_id"] != Guild.id:
                    return None
                return await get_or_fetch_channel(self.bot, post["post_id"])
        except (OSError, aiohttp.ClientError, discord.HTTPException):
            # Thread notices are best-effort, they shouldn't stop the kicks.
            log.exception("Failed to get the modmail thread for %d.", user.id)
            return None

    async def _notify_thread(self, user: discord.abc.Snowflake, description: str, colour: int) -> bool:
        """Post a notice in the user's modmail thread. Return whether they had a thread to post in."""
        thread = await self._get_thread(user)
        if not thread:
            return False
        await thread.send(embed=discord.Embed(description=description, colour=colour))
        return True

    async def _maybe_kick_user(self, member: discord.Member) -> bool:
        """
        Kick the member from the appeals server unless they are banned in PyDis or are staff.

        Return whether the member was kicked.
        """
        if member.bot or await self._is_banned_pydis(member):
            return False

        if await self._can_bypass_kick(member):
            log.info("Not kicking %s (%d) as they have a bypass role", member, member.id)
            return False

        try:
            await member.kick(reason="Not banned in main server")
        except discord.Forbidden:
            log.error("Failed to kick %s (%d) due to insufficient permissions.", member, member.id)
            return False

        await self.logs_channel.send(f"Kicked {member} ({member.id}) on join as they're not banned in main server.")
        log.info("Kicked %s (%d).", member, member.id)

        if await self._notify_thread(
            member,
            "The recipient joined the appeals server and has been automatically kicked.",
            Colours.soft_red,
        ):
            self.ignore_next_remove_event.add(member.id)
        return True

    async def _handle_pydis_join(self, member: discord.Member) -> None:
        """Kick the member from the appeals server now that they're back in PyDis."""
        appeals_member = await members.get_or_fetch_member(self.appeals_guild, member.id)
        if not appeals_member:
            return

        await appeals_member.kick(reason="Rejoined PyDis")
        await self.logs_channel.send(f"Kicked {member} ({member.id}) as they rejoined PyDis.")
        log.info("Kicked %s (%d) as they rejoined PyDis.", member, member.id)

        if await self._notify_thread(
            member,
            "The recipient has been kicked from the appeals server.",
            Colours.soft_red,
        ):
            self.ignore_next_remove_event.add(member.id)

    async def _handle_appeals_join(self, member: discord.Member) -> None:
        """Kick the member if they shouldn't be in the appeals server, otherwise post that they joined."""
        if not await self._maybe_kick_user(member):
            await self._notify_thread(member, "The recipient has joined the appeals server.", Colours.soft_green)

    async def _handle_remove(self, member: discord.Member) -> None:
        """Post that the member left the appeals server, unless we were the ones who kicked them."""
        if member.guild != self.appeals_guild:
            return

        if member.id in self.ignore_next_remove_event:
            self.ignore_next_remove_event.discard(member.id)
            return

        await self._notify_thread(member, "The recipient has left the appeals server.", Colours.soft_red)

    def _user_lock(self, user_id: int) -> asyncio.Lock:
        """Return the user's lock, so their join and leave events are handled one at a time, in order."""
        return self.user_locks.setdefault(user_id, asyncio.Lock())

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Handle a member joining either PyDis or the appeals server."""
        async with self._user_lock(member.id):
            if member.guild == self.pydis_guild:
                await self._handle_pydis_join(member)
            elif member.guild == self.appeals_guild:
                await self._handle_appeals_join(member)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Handle a member leaving the appeals server."""
        async with self._user_lock(member.id):
            await self._handle_remove(member)


async def setup(bot: Bot) -> None:
    """Load the BanAppeals cog."""
    await bot.add_cog(BanAppeals(bot))
