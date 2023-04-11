from typing import ClassVar, Union

from discord import Member

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings_types.settings_entry import ValidationEntry


class RoleBypass(ValidationEntry):
    """A setting entry which tells whether the roles the member has allow them to bypass the filter."""

    name: ClassVar[str] = "bypass_roles"
    description: ClassVar[str] = "A list of role IDs or role names. Users with these roles will not trigger the filter."

    bypass_roles: set[Union[int, str]]  # noqa: UP007

    def triggers_on(self, ctx: FilterContext) -> bool:
        """Return whether the filter should be triggered on this user given their roles."""
        if not isinstance(ctx.author, Member):
            return True
        return all(
            member_role.id not in self.bypass_roles and member_role.name not in self.bypass_roles
            for member_role in ctx.author.roles
        )
