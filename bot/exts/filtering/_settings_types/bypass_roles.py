from typing import Any

from discord import Member

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings_types.settings_entry import ValidationEntry


class RoleBypass(ValidationEntry):
    """A setting entry which tells whether the roles the member has allow them to bypass the filter."""

    name = "bypass_roles"
    description = "A list of role IDs or role names. Users with these roles will not trigger the filter."

    def __init__(self, entry_data: Any):
        super().__init__(entry_data)
        self.bypass_roles = set()
        for role in entry_data:
            if role.isdigit():
                self.bypass_roles.add(int(role))
            else:
                self.bypass_roles.add(role)

    def triggers_on(self, ctx: FilterContext) -> bool:
        """Return whether the filter should be triggered on this user given their roles."""
        if not isinstance(ctx.author, Member):
            return True
        return all(
            member_role.id not in self.bypass_roles and member_role.name not in self.bypass_roles
            for member_role in ctx.author.roles
        )
