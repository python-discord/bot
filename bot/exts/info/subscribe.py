import calendar
import operator
from dataclasses import dataclass

import arrow
import discord
from discord.ext import commands
from discord.interactions import Interaction
from pydis_core.utils import members

from bot import constants
from bot.bot import Bot
from bot.decorators import redirect_output
from bot.log import get_logger
from bot.utils.channel import get_or_fetch_channel


@dataclass(frozen=True)
class AssignableRole:
    """
    A role that can be assigned to a user.

    months_available is a tuple that signifies what months the role should be
    self-assignable, using None for when it should always be available.
    """

    role_id: int
    months_available: tuple[int] | None
    name: str | None = None  # This gets populated within Subscribe.cog_load()

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
    AssignableRole(constants.Roles.legacy_help_channels_access, None),
    AssignableRole(constants.Roles.lovefest, (1, 2)),
    AssignableRole(constants.Roles.advent_of_code, (11, 12)),
    AssignableRole(constants.Roles.revival_of_code, (7, 8, 9, 10)),
)

ITEMS_PER_ROW = 3
DELETE_MESSAGE_AFTER = 300  # Seconds

log = get_logger(__name__)


class RoleButtonView(discord.ui.View):
    """
    A view that holds the list of SingleRoleButtons to show to the member.

    Attributes
    __________
    interaction_owner: discord.Member
        The member that initiated the interaction
    """

    interaction_owner: discord.Member

    def __init__(self, member: discord.Member, assignable_roles: list[AssignableRole]):
        super().__init__(timeout=DELETE_MESSAGE_AFTER)
        self.interaction_owner = member
        author_roles = [role.id for role in member.roles]

        for index, role in enumerate(assignable_roles):
            row = index // ITEMS_PER_ROW
            self.add_item(SingleRoleButton(role, role.role_id in author_roles, row))

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
    """A button that adds or removes a role from the member depending on its current state."""

    ADD_STYLE = discord.ButtonStyle.success
    REMOVE_STYLE = discord.ButtonStyle.red
    UNAVAILABLE_STYLE = discord.ButtonStyle.secondary
    LABEL_FORMAT = "{action} role {role_name}"

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
        await interaction.followup.send(
            self.LABEL_FORMAT.format(action="Added" if self.assigned else "Removed", role_name=self.role.name),
            ephemeral=True,
        )

    async def update_view(self, interaction: Interaction) -> None:
        """Updates the original interaction message with a new view object with the updated buttons."""
        self.style = self.REMOVE_STYLE if self.assigned else self.ADD_STYLE
        self.label = self.LABEL_FORMAT.format(action="Remove" if self.assigned else "Add", role_name=self.role.name)
        try:
            await interaction.response.edit_message(view=self.view)
        except discord.NotFound:
            log.debug("Subscribe message for %s removed before buttons could be updated", interaction.user)
            self.view.stop()


class AllSelfAssignableRolesView(discord.ui.View):
    """A persistent view that'll hold one button allowing interactors to toggle all available self-assignable roles."""

    def __init__(self, assignable_roles: list[AssignableRole]):
        super().__init__(timeout=None)
        self.assignable_roles = assignable_roles

    @discord.ui.button(
        style=discord.ButtonStyle.success,
        label="Show all self assignable roles",
        custom_id="toggle-available-roles-button",
        row=1
    )
    async def show_all_self_assignable_roles(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Sends the original subscription view containing the available self assignable roles."""
        view = RoleButtonView(interaction.user, self.assignable_roles)
        await interaction.response.send_message(
            view=view,
            ephemeral=True
        )


class Subscribe(commands.Cog):
    """Cog to allow user to self-assign & remove the roles present in ASSIGNABLE_ROLES."""

    GREETING_EMOJI = ":wave:"

    SELF_ASSIGNABLE_ROLES_MESSAGE = (
        f"Hi there {GREETING_EMOJI},"
        "\nWe have self-assignable roles for server updates and events!"
        "\nClick the button below to toggle them:"
    )

    def __init__(self, bot: Bot):
        self.bot = bot
        self.assignable_roles: list[AssignableRole] = []
        self.guild: discord.Guild = None

    async def cog_load(self) -> None:
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

        placeholder_message_view_tuple = await self._fetch_or_create_self_assignable_roles_message()
        self_assignable_roles_message, self_assignable_roles_view = placeholder_message_view_tuple
        self._attach_persistent_roles_view(self_assignable_roles_message, self_assignable_roles_view)

    @commands.cooldown(1, 10, commands.BucketType.member)
    @commands.command(name="subscribe", aliases=("unsubscribe",))
    @redirect_output(
        destination_channel=constants.Channels.bot_commands,
        bypass_roles=constants.STAFF_PARTNERS_COMMUNITY_ROLES,
    )
    async def subscribe_command(self, ctx: commands.Context, *_) -> None:  # We don't actually care about the args
        """Display the member's current state for each role, and allow them to add/remove the roles."""
        view = RoleButtonView(ctx.author, self.assignable_roles)
        await ctx.send(
            "Click the buttons below to add or remove your roles!",
            view=view,
            delete_after=DELETE_MESSAGE_AFTER
        )

    async def _fetch_or_create_self_assignable_roles_message(self) -> tuple[discord.Message, discord.ui.View | None]:
        """
        Fetches the message that holds the self assignable roles view.

        If the initial message isn't found, a new one will be created.
        This message will always be needed to attach the persistent view to it
        """
        roles_channel: discord.TextChannel = await get_or_fetch_channel(constants.Channels.roles)

        async for message in roles_channel.history(limit=30):
            if message.content == self.SELF_ASSIGNABLE_ROLES_MESSAGE:
                log.debug(f"Found self assignable roles view message: {message.id}")
                return message, None

        log.debug("Self assignable roles view message hasn't been found, creating a new one.")
        view = AllSelfAssignableRolesView(self.assignable_roles)
        placeholder_message = await roles_channel.send(self.SELF_ASSIGNABLE_ROLES_MESSAGE, view=view)
        return placeholder_message, view

    def _attach_persistent_roles_view(
            self,
            placeholder_message: discord.Message,
            persistent_roles_view: discord.ui.View | None = None
    ) -> None:
        """
        Attaches the persistent view that toggles self assignable roles to its placeholder message.

        The message is searched for/created upon loading the Cog.

        Parameters
        __________
            :param placeholder_message: The message that will hold the persistent view allowing
            users to toggle the RoleButtonView
            :param persistent_roles_view: The view attached to the placeholder_message
            If none, a new view will be created
        """
        if not persistent_roles_view:
            persistent_roles_view = AllSelfAssignableRolesView(self.assignable_roles)

        self.bot.add_view(persistent_roles_view, message_id=placeholder_message.id)


async def setup(bot: Bot) -> None:
    """Load the 'Subscribe' cog."""
    if len(ASSIGNABLE_ROLES) > ITEMS_PER_ROW * 5:  # Discord limits views to 5 rows of buttons.
        log.error("Too many roles for 5 rows, not loading the Subscribe cog.")
    else:
        await bot.add_cog(Subscribe(bot))
