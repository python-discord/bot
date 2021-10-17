import arrow
import discord
from discord.ext import commands
from discord.interactions import Interaction

from bot import constants
from bot.bot import Bot
from bot.decorators import in_whitelist
from bot.log import get_logger
from bot.utils import checks, members, scheduling

# Tuple of tuples, where each inner tuple is a role id and a month number.
# The month number signifies what month the role should be assignable,
# use None for the month number if it should always be active.
ASSIGNABLE_ROLES = (
    (constants.Roles.announcements, None),
    (constants.Roles.pyweek_announcements, None),
    (constants.Roles.lovefest, 2),
    (constants.Roles.advent_of_code, 12),
)
ITEMS_PER_ROW = 3

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
    REMOVE_STYLE = discord.ButtonStyle.secondary
    LABEL_FORMAT = "{action} role {role_name}"
    CUSTOM_ID_FORMAT = "subscribe-{role_id}"

    def __init__(self, role: discord.Role, assigned: bool, row: int):
        super().__init__(
            style=self.REMOVE_STYLE if assigned else self.ADD_STYLE,
            label=self.LABEL_FORMAT.format(action="Remove" if assigned else "Add", role_name=role.name),
            custom_id=self.CUSTOM_ID_FORMAT.format(role_id=role.id),
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

        await members.handle_role_change(
            interaction.user,
            interaction.user.remove_roles if self.assigned else interaction.user.add_roles,
            self.role,
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
        self.assignable_roles: list[discord.Role] = []
        self.guild: discord.Guild = None

    async def init_cog(self) -> None:
        """Initialise the cog by resolving the role IDs in ASSIGNABLE_ROLES to role names."""
        await self.bot.wait_until_guild_available()

        current_month = arrow.utcnow().month
        self.guild = self.bot.get_guild(constants.Guild.id)

        for role_id, month_available in ASSIGNABLE_ROLES:
            if month_available is not None and month_available != current_month:
                continue
            role = self.guild.get_role(role_id)
            if role is None:
                log.warning("Could not resolve %d to a role in the guild, skipping.", role_id)
                continue
            self.assignable_roles.append(role)

    @commands.cooldown(1, 10, commands.BucketType.member)
    @commands.command(name="subscribe")
    @in_whitelist(channels=(constants.Channels.bot_commands,))
    async def subscribe_command(self, ctx: commands.Context, *_) -> None:  # We don't actually care about the args
        """Display the member's current state for each role, and allow them to add/remove the roles."""
        await self.init_task

        button_view = RoleButtonView(ctx.author)
        for index, role in enumerate(self.assignable_roles):
            row = index // ITEMS_PER_ROW
            button_view.add_item(SingleRoleButton(role, role in ctx.author.roles, row))

        await ctx.send("Click the buttons below to add or remove your roles!", view=button_view)

    # This cannot be static (must have a __func__ attribute).
    async def cog_command_error(self, ctx: commands.Context, error: Exception) -> None:
        """Check for & ignore any InWhitelistCheckFailure."""
        if isinstance(error, checks.InWhitelistCheckFailure):
            error.handled = True


def setup(bot: Bot) -> None:
    """Load the Subscribe cog."""
    if len(ASSIGNABLE_ROLES) > ITEMS_PER_ROW*5:  # Discord limits views to 5 rows of buttons.
        log.error("Too many roles for 5 rows, not loading the Subscribe cog.")
    else:
        bot.add_cog(Subscribe(bot))
