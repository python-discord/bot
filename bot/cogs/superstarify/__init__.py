import logging
import random
from datetime import datetime

from discord import Colour, Embed, Member
from discord.errors import Forbidden
from discord.ext.commands import Bot, Context, command

from bot.cogs.moderation import Moderation
from bot.cogs.modlog import ModLog
from bot.cogs.superstarify.stars import get_nick
from bot.constants import Icons, MODERATION_ROLES, POSITIVE_REPLIES
from bot.converters import ExpirationDate
from bot.decorators import with_role
from bot.utils.moderation import post_infraction

log = logging.getLogger(__name__)
NICKNAME_POLICY_URL = "https://pythondiscord.com/about/rules#nickname-policy"


class Superstarify:
    """
    A set of commands to moderate terrible nicknames.
    """

    def __init__(self, bot: Bot):
        self.bot = bot

    @property
    def moderation(self) -> Moderation:
        return self.bot.get_cog("Moderation")

    @property
    def modlog(self) -> ModLog:
        return self.bot.get_cog("ModLog")

    async def on_member_update(self, before: Member, after: Member):
        """
        This event will trigger when someone changes their name.
        At this point we will look up the user in our database and check
        whether they are allowed to change their names, or if they are in
        superstar-prison. If they are not allowed, we will change it back.
        """

        if before.display_name == after.display_name:
            return  # User didn't change their nickname. Abort!

        log.trace(
            f"{before.display_name} is trying to change their nickname to {after.display_name}. "
            "Checking if the user is in superstar-prison..."
        )

        active_superstarifies = await self.bot.api_client.get(
            'bot/infractions',
            params={
                'active': 'true',
                'type': 'superstar',
                'user__id': str(before.id)
            }
        )

        if active_superstarifies:
            [infraction] = active_superstarifies
            forced_nick = get_nick(infraction['id'], before.id)
            if after.display_name == forced_nick:
                return  # Nick change was triggered by this event. Ignore.

            log.info(
                f"{after.display_name} is currently in superstar-prison. "
                f"Changing the nick back to {before.display_name}."
            )
            await after.edit(nick=forced_nick)
            end_timestamp_human = (
                datetime.fromisoformat(infraction['expires_at'][:-1])
                .strftime('%c')
            )

            try:
                await after.send(
                    "You have tried to change your nickname on the **Python Discord** server "
                    f"from **{before.display_name}** to **{after.display_name}**, but as you "
                    "are currently in superstar-prison, you do not have permission to do so. "
                    "You will be allowed to change your nickname again at the following time:\n\n"
                    f"**{end_timestamp_human}**."
                )
            except Forbidden:
                log.warning(
                    "The user tried to change their nickname while in superstar-prison. "
                    "This led to the bot trying to DM the user to let them know they cannot do that, "
                    "but the user had either blocked the bot or disabled DMs, so it was not possible "
                    "to DM them, and a discord.errors.Forbidden error was incurred."
                )

    async def on_member_join(self, member: Member):
        """
        This event will trigger when someone (re)joins the server.
        At this point we will look up the user in our database and check
        whether they are in superstar-prison. If so, we will change their name
        back to the forced nickname.
        """

        active_superstarifies = await self.bot.api_client.get(
            'bot/infractions',
            params={
                'active': 'true',
                'type': 'superstar',
                'user__id': member.id
            }
        )

        if active_superstarifies:
            [infraction] = active_superstarifies
            forced_nick = get_nick(infraction['id'], member.id)
            await member.edit(nick=forced_nick)
            end_timestamp_human = (
                datetime.fromisoformat(infraction['expires_at'][:-1]).strftime('%c')
            )

            try:
                await member.send(
                    "You have left and rejoined the **Python Discord** server, effectively resetting "
                    f"your nickname from **{forced_nick}** to **{member.name}**, "
                    "but as you are currently in superstar-prison, you do not have permission to do so. "
                    "Therefore your nickname was automatically changed back. You will be allowed to "
                    "change your nickname again at the following time:\n\n"
                    f"**{end_timestamp_human}**."
                )
            except Forbidden:
                log.warning(
                    "The user left and rejoined the server while in superstar-prison. "
                    "This led to the bot trying to DM the user to let them know their name was restored, "
                    "but the user had either blocked the bot or disabled DMs, so it was not possible "
                    "to DM them, and a discord.errors.Forbidden error was incurred."
                )

            # Log to the mod_log channel
            log.trace("Logging to the #mod-log channel. This could fail because of channel permissions.")
            mod_log_message = (
                f"**{member.name}#{member.discriminator}** (`{member.id}`)\n\n"
                f"Superstarified member potentially tried to escape the prison.\n"
                f"Restored enforced nickname: `{forced_nick}`\n"
                f"Superstardom ends: **{end_timestamp_human}**"
            )
            await self.modlog.send_log_message(
                icon_url=Icons.user_update,
                colour=Colour.gold(),
                title="Superstar member rejoined server",
                text=mod_log_message,
                thumbnail=member.avatar_url_as(static_format="png")
            )

    @command(name='superstarify', aliases=('force_nick', 'star'))
    @with_role(*MODERATION_ROLES)
    async def superstarify(
        self, ctx: Context, member: Member, expiration: ExpirationDate, reason: str = None
    ):
        """
        This command will force a random superstar name (like Taylor Swift) to be the user's
        nickname for a specified duration. An optional reason can be provided.
        If no reason is given, the original name will be shown in a generated reason.
        """

        active_superstarifies = await self.bot.api_client.get(
            'bot/infractions',
            params={
                'active': 'true',
                'type': 'superstar',
                'user__id': str(member.id)
            }
        )
        if active_superstarifies:
            return await ctx.send(
                ":x: According to my records, this user is already superstarified. "
                f"See infraction **#{active_superstarifies[0]['id']}**."
            )

        infraction = await post_infraction(
            ctx, member,
            type='superstar', reason=reason or ('old nick: ' + member.display_name),
            expires_at=expiration
        )
        forced_nick = get_nick(infraction['id'], member.id)

        embed = Embed()
        embed.title = "Congratulations!"
        embed.description = (
            f"Your previous nickname, **{member.display_name}**, was so bad that we have decided to change it. "
            f"Your new nickname will be **{forced_nick}**.\n\n"
            f"You will be unable to change your nickname until \n**{expiration}**.\n\n"
            "If you're confused by this, please read our "
            f"[official nickname policy]({NICKNAME_POLICY_URL})."
        )

        # Log to the mod_log channel
        log.trace("Logging to the #mod-log channel. This could fail because of channel permissions.")
        mod_log_message = (
            f"**{member.name}#{member.discriminator}** (`{member.id}`)\n\n"
            f"Superstarified by **{ctx.author.name}**\n"
            f"Old nickname: `{member.display_name}`\n"
            f"New nickname: `{forced_nick}`\n"
            f"Superstardom ends: **{expiration}**"
        )
        await self.modlog.send_log_message(
            icon_url=Icons.user_update,
            colour=Colour.gold(),
            title="Member Achieved Superstardom",
            text=mod_log_message,
            thumbnail=member.avatar_url_as(static_format="png")
        )

        await self.moderation.notify_infraction(
            user=member,
            infr_type="Superstarify",
            expires_at=expiration,
            reason=f"Your nickname didn't comply with our [nickname policy]({NICKNAME_POLICY_URL})."
        )

        # Change the nick and return the embed
        log.trace("Changing the users nickname and sending the embed.")
        await member.edit(nick=forced_nick)
        await ctx.send(embed=embed)

    @command(name='unsuperstarify', aliases=('release_nick', 'unstar'))
    @with_role(*MODERATION_ROLES)
    async def unsuperstarify(self, ctx: Context, member: Member):
        """
        This command will remove the entry from our database, allowing the user
        to once again change their nickname.

        :param ctx: Discord message context
        :param member: The member to unsuperstarify
        """

        log.debug(f"Attempting to unsuperstarify the following user: {member.display_name}")

        embed = Embed()
        embed.colour = Colour.blurple()

        active_superstarifies = await self.bot.api_client.get(
            'bot/infractions',
            params={
                'active': 'true',
                'type': 'superstar',
                'user__id': str(member.id)
            }
        )
        if not active_superstarifies:
            return await ctx.send(
                ":x: There is no active superstarify infraction for this user."
            )

        [infraction] = active_superstarifies
        await self.bot.api_client.patch(
            'bot/infractions/' + str(infraction['id']),
            json={'active': False}
        )

        embed = Embed()
        embed.description = "User has been released from superstar-prison."
        embed.title = random.choice(POSITIVE_REPLIES)

        await self.moderation.notify_pardon(
            user=member,
            title="You are no longer superstarified.",
            content="You may now change your nickname on the server."
        )
        log.trace(f"{member.display_name} was successfully released from superstar-prison.")
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Superstarify(bot))
    log.info("Cog loaded: Superstarify")
