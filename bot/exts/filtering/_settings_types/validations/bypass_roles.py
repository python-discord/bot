from collections.abc import Sequence
from typing import ClassVar

from discord import Member
from pydantic import field_validator

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings_types.settings_entry import ValidationEntry


class RoleBypass(ValidationEntry):
    """A setting entry which tells whether the roles the member has allow them to bypass the filter."""

    name: ClassVar[str] = "bypass_roles"
    description: ClassVar[str] = "A list of role IDs or role names. Users with these roles will not trigger the filter."

    bypass_roles: set[int | str]

    @field_validator("bypass_roles", mode="before")
    @classmethod
    def init_if_bypass_roles_none(cls, bypass_roles: Sequence[int | str] | None) -> Sequence[int | str]:
        """
        Initialize an empty sequence if the value is None.

        This also coerces each element of bypass_roles to an int, if possible.
        """
        if bypass_roles is None:
            return []

        def _coerce_to_int(input: int | str) -> int | str:
            try:
                return int(input)
            except ValueError:
                return input

        return map(_coerce_to_int, bypass_roles)

    def triggers_on(self, ctx: FilterContext) -> bool:
        """Return whether the filter should be triggered on this user given their roles."""
        if not isinstance(ctx.author, Member):
            return True
        return all(
            member_role.id not in self.bypass_roles and member_role.name not in self.bypass_roles
            for member_role in ctx.author.roles
        )
