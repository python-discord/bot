from typing import Hashable, Union

from discord import Member, User


class LockedResourceError(RuntimeError):
    """
    Exception raised when an operation is attempted on a locked resource.

    Attributes:
        `type` -- name of the locked resource's type
        `id` -- ID of the locked resource
    """

    def __init__(self, resource_type: str, resource_id: Hashable):
        self.type = resource_type
        self.id = resource_id

        super().__init__(
            f"Cannot operate on {self.type.lower()} `{self.id}`; "
            "it is currently locked and in use by another operation."
        )


class InvalidInfractedUserError(Exception):
    """
    Exception raised upon attempt of infracting an invalid user.

    Attributes:
        `user` -- User or Member which is invalid
    """

    def __init__(self, user: Union[Member, User], reason: str = "User infracted is a bot."):
        self.user = user
        self.reason = reason

        super().__init__(reason)


class BrandingMisconfiguration(RuntimeError):
    """Raised by the Branding cog when a misconfigured event is encountered."""

    pass


class NonExistentRoleError(ValueError):
    """
    Raised by the Information Cog when encountering a role that does not exist.

    Attributes:
        `role_id` -- the ID of the role that does not exist
    """

    def __init__(self, role_id: int):
        super().__init__(f"Could not fetch data for role {role_id}")

        self.role_id = role_id
