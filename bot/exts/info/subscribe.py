import calendar
import operator
import typing as t
from dataclasses import dataclass

import arrow
import discord
from botcore.utils import members, scheduling
from discord.ext import commands
from discord.interactions import Interaction

from bot import constants
from bot.bot import Bot
from bot.decorators import redirect_output
from bot.log import get_logger


@dataclass(frozen=True)
class AssignableRole:
    """
    A role that can be assigned to a user.

    months_available is a tuple that signifies what months the role should be
    self-assignable, using None for when it should always be available.
    """

    role_id: int
    months_available: t.Optional[tuple[int]]
    name: t.Optional[str] = None  # This gets populated within Subscribe.init_cog()

    def is_currently_available(self) -> bool:
        """Check if the role is available for the current month."""
        if self.months_available is None:
            return True
        return arrow.utcnow().month in self.months_available

    def get_readable_available_months(self) -> str:
        """Get a readable string of the months the role is available."""
        if self.months_available is None:
            return f"{self.name} is always available."

        # Join the months together with comma separators, but use "and" for the final seperator.
        month_names = [calendar.month_name[month] for month in self.months_available]
        available_months_str = ", ".join(month_names[:-1]) + f" and {month_names[-1]}"
        return f"{self.name} can only be assigned during {available_months_str}."


ASSIGNABLE_ROLES = (
    AssignableRole(constants.Roles.announcements, None),
    AssignableRole(constants.Roles.pyweek_announcements, None),
    AssignableRole(constants.Roles.lovefest, (1, 2)),
    AssignableRole(constants.Roles.advent_of_code, (11, 12)),
)

ITEMS_PER_ROW = 3
DELETE_MESSAGE_AFTER = 300  # Seconds

log = get_logger(__name__)


class RoleButtonView(discord.ui.View):
    """A list of SingleRoleButtons to show to the member."""

    def __init__(self, member: discord.Member):
        super().__init__()
        self.interaction_owner = member

    async def interaction_check(self, interaction: Interaction) -> bool:
        """Ensure that the user clicking the button is the member who invoked the command."""
        if interaction.user != self.interaction_owner:
            await interaction.response.send_message(
                ":x: This is not your command to react to!",
                ephemeral=True
            )
            return False
        return True


class SingleRoleButton(discord.ui.Button):
    """A button that adds or removes a role from the member depending on it's current state."""

    ADD_STYLE = discord.ButtonStyle.success
    REMOVE_STYLE = discord.ButtonStyle.red
    UNAVAILABLE_STYLE = discord.ButtonStyle.secondary
    LABEL_FORMAT = "{action} role {role_name}."
    CUSTOM_ID_FORMAT = "subscribe-{role_id}"

    def __init__(self, role: AssignableRole, assigned: bool, row: int):
        if role.is_currently_available():
            style = self.REMOVE_STYLE if assigned else self.ADD_STYLE
            label = self.LABEL_FORMAT.format(action="Remove" if assigned else "Add", role_name=role.name)
        else:
            style = self.UNAVAILABLE_STYLE
            label = f"🔒 {role.name}"

        super().__init__(
            style=style,
            label=label,
            custom_id=self.CUSTOM_ID_FORMAT.format(role_id=role.role_id),
            row=row,
        )
        self.role = role
        self.assigned = assigned

    async def callback(self, interaction: Interaction) -> None:
        """Update the member's role and change button text to reflect current text."""
        if isinstance(interaction.user, discord.User):
            log.trace("User %s is not a member", interaction.user)
            await interaction.message.delete()
            self.view.stop()
            return

        if not self.role.is_currently_available():
            await interaction.response.send_message(self.role.get_readable_available_months(), ephemeral=True)
            return

        await members.handle_role_change(
            interaction.user,
            interaction.user.remove_roles if self.assigned else interaction.user.add_roles,
            discord.Object(self.role.role_id),
        )

        self.assigned = not self.assigned
        await self.update_view(interaction)
        await interaction.response.send_message(
            self.LABEL_FORMAT.format(action="Added" if self.assigned else "Removed", role_name=self.role.name),
            ephemeral=True,
        )

    async def update_view(self, interaction: Interaction) -> None:
        """Updates the original interaction message with a new view object with the updated buttons."""
        self.style = self.REMOVE_STYLE if self.assigned else self.ADD_STYLE
        self.label = self.LABEL_FORMAT.format(action="Remove" if self.assigned else "Add", role_name=self.role.name)
        try:
            await interaction.message.edit(view=self.view)
        except discord.NotFound:
            log.debug("Subscribe message for %s removed before buttons could be updated", interaction.user)
            self.view.stop()


class Subscribe(commands.Cog):
    """Cog to allow user to self-assign & remove the roles present in ASSIGNABLE_ROLES."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.init_task = scheduling.create_task(self.init_cog(), event_loop=self.bot.loop)
        self.assignable_roles: list[AssignableRole] = []
        self.guild: discord.Guild = None

    async def init_cog(self) -> None:
        """Initialise the cog by resolving the role IDs in ASSIGNABLE_ROLES to role names."""
        await self.bot.wait_until_guild_available()

        self.guild = self.bot.get_guild(constants.Guild.id)

        for role in ASSIGNABLE_ROLES:
            discord_role = self.guild.get_role(role.role_id)
            if discord_role is None:
                log.warning("Could not resolve %d to a role in the guild, skipping.", role.role_id)
                continue
            self.assignable_roles.append(
                AssignableRole(
                    role_id=role.role_id,
                    months_available=role.months_available,
                    name=discord_role.name,
                )
            )

        # Sort by role name, then shift unavailable roles to the end of the list
        self.assignable_roles.sort(key=operator.attrgetter("name"))
        self.assignable_roles.sort(key=operator.methodcaller("is_currently_available"), reverse=True)

    @commands.cooldown(1, 10, commands.BucketType.member)
    @commands.command(name="subscribe", aliases=("unsubscribe",))
    @redirect_output(
        destination_channel=constants.Channels.bot_commands,
        bypass_roles=constants.STAFF_PARTNERS_COMMUNITY_ROLES,
    )
    async def subscribe_command(self, ctx: commands.Context, *_) -> None:  # We don't actually care about the args
        """Display the member's current state for each role, and allow them to add/remove the roles."""
        await self.init_task

        button_view = RoleButtonView(ctx.author)
        author_roles = [role.id for role in ctx.author.roles]
        for index, role in enumerate(self.assignable_roles):
            row = index // ITEMS_PER_ROW
            button_view.add_item(SingleRoleButton(role, role.role_id in author_roles, row))

        await ctx.send(
            "Click the buttons below to add or remove your roles!",
            view=button_view,
            delete_after=DELETE_MESSAGE_AFTER,
        )


def setup(bot: Bot) -> None:
    """Load the Subscribe cog."""
    if len(ASSIGNABLE_ROLES) > ITEMS_PER_ROW*5:  # Discord limits views to 5 rows of buttons.
        log.error("Too many roles for 5 rows, not loading the Subscribe cog.")
    else:
        bot.add_cog(Subscribe(bot))
