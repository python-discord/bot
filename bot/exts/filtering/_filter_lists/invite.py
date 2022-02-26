from __future__ import annotations

import typing
from functools import reduce
from operator import or_
from typing import Optional

from botcore.regex import DISCORD_INVITE
from discord import Embed, Invite
from discord.errors import NotFound

import bot
from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filter_lists.filter_list import FilterList, ListType
from bot.exts.filtering._filters.invite import InviteFilter
from bot.exts.filtering._settings import ActionSettings
from bot.exts.filtering._utils import clean_input

if typing.TYPE_CHECKING:
    from bot.exts.filtering.filtering import Filtering


class InviteList(FilterList):
    """A list of filters, each looking for guild invites to a specific guild."""

    name = "invite"

    def __init__(self, filtering_cog: Filtering):
        super().__init__(InviteFilter)
        filtering_cog.subscribe(self, Event.MESSAGE)

    async def actions_for(self, ctx: FilterContext) -> tuple[Optional[ActionSettings], Optional[str]]:
        """Dispatch the given event to the list's filters, and return actions to take and a message to relay to mods."""
        _, failed = self.defaults[ListType.ALLOW]["validations"].evaluate(ctx)
        if failed:  # There's no invite filtering in this context.
            return None, ""

        text = clean_input(ctx.content)

        # Avoid escape characters
        text = text.replace("\\", "")

        matches = list(DISCORD_INVITE.finditer(text))
        invite_codes = {m.group("invite") for m in matches}
        if not invite_codes:
            return None, ""

        # Sort the invites into three categories:
        denied_by_default = dict()  # Denied unless whitelisted.
        allowed_by_default = dict()  # Allowed unless blacklisted (partnered or verified servers).
        disallowed_invites = dict()  # Always denied (invalid invites).
        for invite_code in invite_codes:
            try:
                invite = await bot.instance.fetch_invite(invite_code)
            except NotFound:
                disallowed_invites[invite_code] = None
            else:
                if not invite.guild:
                    disallowed_invites[invite_code] = invite
                else:
                    if "PARTNERED" in invite.guild.features or "VERIFIED" in invite.guild.features:
                        allowed_by_default[invite_code] = invite
                    else:
                        denied_by_default[invite_code] = invite

        # Add the disallowed by default unless they're whitelisted.
        guilds_for_inspection = {invite.guild.id for invite in denied_by_default.values()}
        new_ctx = ctx.replace(content=guilds_for_inspection)
        allowed = {filter_.content for filter_ in self.filter_lists[ListType.ALLOW] if filter_.triggered_on(new_ctx)}
        disallowed_invites.update({
            invite_code: invite for invite_code, invite in denied_by_default.items() if invite.guild.id not in allowed
        })

        # Add the allowed by default only if they're blacklisted.
        guilds_for_inspection = {invite.guild.id for invite in allowed_by_default.values()}
        new_ctx = ctx.replace(content=guilds_for_inspection)
        triggered = self.filter_list_result(
            new_ctx, self.filter_lists[ListType.ALLOW], self.defaults[ListType.DENY]["validations"]
        )
        disallowed_invites.update({
            invite_code: invite for invite_code, invite in allowed_by_default.items()
            if invite.guild.id in {filter_.content for filter_ in triggered}
        })

        if not disallowed_invites:
            return None, ""

        actions = None
        if len(disallowed_invites) > len(triggered):  # There are invites which weren't allowed but aren't blacklisted.
            actions = reduce(or_, (filter_.actions for filter_ in triggered), self.defaults[ListType.ALLOW]["actions"])
        elif triggered:
            actions = reduce(or_, (filter_.actions for filter_ in triggered))
        ctx.matches += {match[0] for match in matches if match.group("invite") in disallowed_invites}
        ctx.alert_embeds += (self._guild_embed(invite) for invite in disallowed_invites.values() if invite)
        return actions, ", ".join(f"`{invite}`" for invite in disallowed_invites)

    @staticmethod
    def _guild_embed(invite: Invite) -> Embed:
        """Return an embed representing the guild invites to."""
        embed = Embed()
        if invite.guild:
            embed.title = invite.guild.name
            embed.set_thumbnail(url=invite.guild.icon.url)
            embed.set_footer(text=f"Guild ID: {invite.guild.id}")
        else:
            embed.title = "Group DM"

        embed.description = (
            f"**Invite Code:** {invite.code}\n"
            f"**Members:** {invite.approximate_member_count}\n"
            f"**Active:** {invite.approximate_presence_count}"
        )

        return embed
