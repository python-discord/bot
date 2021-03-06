import json
import logging
import random
import textwrap
import typing as t
from pathlib import Path

from discord import Embed, Member
from discord.ext.commands import Cog, Context, command, has_any_role
from discord.utils import escape_markdown

from bot import constants
from bot.bot import Bot
from bot.converters import Expiry
from bot.exts.moderation.infraction import _utils
from bot.exts.moderation.infraction._scheduler import InfractionScheduler
from bot.utils.messages import format_user
from bot.utils.time import format_infraction

log = logging.getLogger(__name__)
NICKNAME_POLICY_URL = "https://pythondiscord.com/pages/rules/#nickname-policy"

with Path("bot/resources/stars.json").open(encoding="utf-8") as stars_file:
    STAR_NAMES = json.load(stars_file)


class Superstarify(InfractionScheduler, Cog):
    """A set of commands to moderate terrible nicknames."""

    def __init__(self, bot: Bot):
        super().__init__(bot, supported_infractions={"superstar"})

    @Cog.listener()
    async def on_member_update(self, before: Member, after: Member) -> None:
        """Revert nickname edits if the user has an active superstarify infraction."""
        if before.display_name == after.display_name:
            return  # User didn't change their nickname. Abort!

        log.trace(
            f"{before} ({before.display_name}) is trying to change their nickname to "
            f"{after.display_name}. Checking if the user is in superstar-prison..."
        )

        active_superstarifies = await self.bot.api_client.get(
            "bot/infractions",
            params={
                "active": "true",
                "type": "superstar",
                "user__id": str(before.id)
            }
        )

        if not active_superstarifies:
            log.trace(f"{before} has no active superstar infractions.")
            return

        infraction = active_superstarifies[0]
        forced_nick = self.get_nick(infraction["id"], before.id)
        if after.display_name == forced_nick:
            return  # Nick change was triggered by this event. Ignore.

        log.info(
            f"{after.display_name} ({after.id}) tried to escape superstar prison. "
            f"Changing the nick back to {before.display_name}."
        )
        await after.edit(
            nick=forced_nick,
            reason=f"Superstarified member tried to escape the prison: {infraction['id']}"
        )

        notified = await _utils.notify_infraction(
            user=after,
            infr_type="Superstarify",
            expires_at=format_infraction(infraction["expires_at"]),
            reason=(
                "You have tried to change your nickname on the **Python Discord** server "
                f"from **{before.display_name}** to **{after.display_name}**, but as you "
                "are currently in superstar-prison, you do not have permission to do so."
            ),
            icon_url=_utils.INFRACTION_ICONS["superstar"][0]
        )

        if not notified:
            log.info("Failed to DM user about why they cannot change their nickname.")

    @Cog.listener()
    async def on_member_join(self, member: Member) -> None:
        """Reapply active superstar infractions for returning members."""
        active_superstarifies = await self.bot.api_client.get(
            "bot/infractions",
            params={
                "active": "true",
                "type": "superstar",
                "user__id": member.id
            }
        )

        if active_superstarifies:
            infraction = active_superstarifies[0]
            action = member.edit(
                nick=self.get_nick(infraction["id"], member.id),
                reason=f"Superstarified member tried to escape the prison: {infraction['id']}"
            )

            await self.reapply_infraction(infraction, action)

    @command(name="superstarify", aliases=("force_nick", "star", "starify", "superstar"))
    async def superstarify(
        self,
        ctx: Context,
        member: Member,
        duration: Expiry,
        *,
        reason: str = '',
    ) -> None:
        """
        Temporarily force a random superstar name (like Taylor Swift) to be the user's nickname.

        A unit of time should be appended to the duration.
        Units (∗case-sensitive):
        \u2003`y` - years
        \u2003`m` - months∗
        \u2003`w` - weeks
        \u2003`d` - days
        \u2003`h` - hours
        \u2003`M` - minutes∗
        \u2003`s` - seconds

        Alternatively, an ISO 8601 timestamp can be provided for the duration.

        An optional reason can be provided, which would be added to a message stating their old nickname
        and linking to the nickname policy.
        """
        if await _utils.get_active_infraction(ctx, member, "superstar"):
            return

        # Post the infraction to the API
        old_nick = member.display_name
        infraction_reason = f'Old nickname: {old_nick}. {reason}'
        infraction = await _utils.post_infraction(ctx, member, "superstar", infraction_reason, duration, active=True)
        id_ = infraction["id"]

        forced_nick = self.get_nick(id_, member.id)
        expiry_str = format_infraction(infraction["expires_at"])

        # Apply the infraction
        async def action() -> None:
            log.debug(f"Changing nickname of {member} to {forced_nick}.")
            self.mod_log.ignore(constants.Event.member_update, member.id)
            await member.edit(nick=forced_nick, reason=reason)

        old_nick = escape_markdown(old_nick)
        forced_nick = escape_markdown(forced_nick)

        nickname_info = textwrap.dedent(f"""
            Old nickname: `{old_nick}`
            New nickname: `{forced_nick}`
        """).strip()

        user_message = (
            f"Your previous nickname, **{old_nick}**, "
            f"was so bad that we have decided to change it. "
            f"Your new nickname will be **{forced_nick}**.\n\n"
            "{reason}"
            f"You will be unable to change your nickname until **{expiry_str}**. "
            "If you're confused by this, please read our "
            f"[official nickname policy]({NICKNAME_POLICY_URL})."
        ).format

        successful = await self.apply_infraction(
            ctx, infraction, member, action(),
            user_reason=user_message(reason=f'**Additional details:** {reason}\n\n' if reason else ''),
            additional_info=nickname_info
        )

        # Send an embed with to the invoking context if superstar was successful.
        if successful:
            log.trace(f"Sending superstar #{id_} embed.")
            embed = Embed(
                title="Superstarified!",
                colour=constants.Colours.soft_orange,
                description=user_message(reason='')
            )
            await ctx.send(embed=embed)

    @command(name="unsuperstarify", aliases=("release_nick", "unstar", "unstarify", "unsuperstar"))
    async def unsuperstarify(self, ctx: Context, member: Member) -> None:
        """Remove the superstarify infraction and allow the user to change their nickname."""
        await self.pardon_infraction(ctx, "superstar", member)

    async def _pardon_action(self, infraction: _utils.Infraction) -> t.Optional[t.Dict[str, str]]:
        """Pardon a superstar infraction and return a log dict."""
        if infraction["type"] != "superstar":
            return

        guild = self.bot.get_guild(constants.Guild.id)
        user = guild.get_member(infraction["user"])

        # Don't bother sending a notification if the user left the guild.
        if not user:
            log.debug(
                "User left the guild and therefore won't be notified about superstar "
                f"{infraction['id']} pardon."
            )
            return {}

        # DM the user about the expiration.
        notified = await _utils.notify_pardon(
            user=user,
            title="You are no longer superstarified",
            content="You may now change your nickname on the server.",
            icon_url=_utils.INFRACTION_ICONS["superstar"][1]
        )

        return {
            "Member": format_user(user),
            "DM": "Sent" if notified else "**Failed**"
        }

    @staticmethod
    def get_nick(infraction_id: int, member_id: int) -> str:
        """Randomly select a nickname from the Superstarify nickname list."""
        log.trace(f"Choosing a random nickname for superstar #{infraction_id}.")

        rng = random.Random(str(infraction_id) + str(member_id))
        return rng.choice(STAR_NAMES)

    # This cannot be static (must have a __func__ attribute).
    async def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators to invoke the commands in this cog."""
        return await has_any_role(*constants.MODERATION_ROLES).predicate(ctx)


def setup(bot: Bot) -> None:
    """Load the Superstarify cog."""
    bot.add_cog(Superstarify(bot))
