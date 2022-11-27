import calendar
import operator
import typing as t
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
    months_available: t.Optional[tuple[int]]
    name: t.Optional[str] = None  # This gets populated within Subscribe.cog_load()

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
    AssignableRole(constants.Roles.revival_of_code, (7, 8, 9, 10)),
)

ITEMS_PER_ROW = 3
DELETE_MESSAGE_AFTER = 300  # Seconds

log = get_logger(__name__)


class RoleButtonView(discord.ui.View):
    """A list of SingleRoleButtons to show to the member."""

    def __init__(self, member: discord.Member):
        super().__init__(timeout=DELETE_MESSAGE_AFTER)
        # We can't obtain the reference to the message before the view is sent
        self.original_message = None
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

    async def on_timeout(self) -> None:
        """Delete the original message that the view was sent along with."""
        await self.original_message.delete()


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


class AllSelfAssignableRolesView(discord.ui.View):
    """A view that'll hold one button allowing interactors to get all available self-assignable roles."""

    def __init__(self):
        super(AllSelfAssignableRolesView, self).__init__(timeout=None)


class ShowAllSelfAssignableRolesButton(discord.ui.Button):
    """A button that sends a view containing all the different roles a user can self assign at that time."""

    CUSTOM_ID = "gotta-claim-them-all"

    def __init__(self, assignable_roles: list[AssignableRole]):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="Show all self assignable roles",
            custom_id=self.CUSTOM_ID,
            row=1
        )
        self.assignable_roles = assignable_roles

    async def callback(self, interaction: Interaction) -> t.Any:
        """Sends the original subscription view containing the available self assignable roles."""
        await interaction.response.defer()
        view = prepare_available_role_subscription_view(interaction, self.assignable_roles)
        message = await interaction.followup.send(
            view=view,
        )
        # Keep reference of the message that contains the view to be deleted
        view.original_message = message


class Subscribe(commands.Cog):
    """Cog to allow user to self-assign & remove the roles present in ASSIGNABLE_ROLES."""

    SELF_ASSIGNABLE_ROLES_MESSAGE = "Click on this button to show all self assignable roles"

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

        initial_self_assignable_roles_message = await self.__search_for_self_assignable_roles_message()
        self.__attach_view_to_initial_self_assignable_roles_message(initial_self_assignable_roles_message)

    @commands.cooldown(1, 10, commands.BucketType.member)
    @commands.command(name="subscribe", aliases=("unsubscribe",))
    @redirect_output(
        destination_channel=constants.Channels.bot_commands,
        bypass_roles=constants.STAFF_PARTNERS_COMMUNITY_ROLES,
    )
    async def subscribe_command(self, ctx: commands.Context, *_) -> None:  # We don't actually care about the args
        """Display the member's current state for each role, and allow them to add/remove the roles."""
        view = prepare_available_role_subscription_view(ctx, self.assignable_roles)

        message = await ctx.send(
            "Click the buttons below to add or remove your roles!",
            view=view,
        )
        # Keep reference of the message that contains the view to be deleted
        view.original_message = message

    async def __search_for_self_assignable_roles_message(self) -> discord.Message:
        """
        Searches for the message that holds the self assignable roles view.

        If the initial message isn't found, a new one will be created.
        This message will always be needed to attach the persistent view to it
        """
        roles_channel = await get_or_fetch_channel(constants.Channels.roles)

        async for message in roles_channel.history(limit=30):
            if message.content == self.SELF_ASSIGNABLE_ROLES_MESSAGE:
                log.debug(f"Found self assignable roles view message: {message.id}")
                return message

        log.debug("Self assignable roles view message hasn't been found, creating a new one.")
        view = AllSelfAssignableRolesView()
        view.add_item(ShowAllSelfAssignableRolesButton(self.assignable_roles))
        return await roles_channel.send(self.SELF_ASSIGNABLE_ROLES_MESSAGE, view=view)

    def __attach_view_to_initial_self_assignable_roles_message(self, message: discord.Message) -> None:
        """
        Attaches the persistent self assignable roles view.

        The message is searched for/created upon loading the Cog.
        """
        view = AllSelfAssignableRolesView()
        view.add_item(ShowAllSelfAssignableRolesButton(self.assignable_roles))
        self.bot.add_view(view, message_id=message.id)


def prepare_available_role_subscription_view(
        trigger_action: commands.Context | Interaction,
        assignable_roles: list[AssignableRole]
) -> discord.ui.View:
    """Prepares the view containing the self assignable roles before its sent."""
    author = trigger_action.author if isinstance(trigger_action, commands.Context) else trigger_action.user
    author_roles = [role.id for role in author.roles]
    button_view = RoleButtonView(member=author)
    button_view.original_message = trigger_action.message

    for index, role in enumerate(assignable_roles):
        row = index // ITEMS_PER_ROW
        button_view.add_item(SingleRoleButton(role, role.role_id in author_roles, row))

    return button_view


async def setup(bot: Bot) -> None:
    """Load the Subscribe cog."""
    if len(ASSIGNABLE_ROLES) > ITEMS_PER_ROW*5:  # Discord limits views to 5 rows of buttons.
        log.error("Too many roles for 5 rows, not loading the Subscribe cog.")
    else:
        await bot.add_cog(Subscribe(bot))
