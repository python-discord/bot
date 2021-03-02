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


class InvalidInfractedUser(Exception):
    """
    Exception raised upon attempt of infracting an invalid user.

    Attributes:
        `user` -- User or Member which is invalid
    """

    def __init__(self, user: Union[Member, User], reason: str = "User infracted is a bot."):
        self.user = user
        self.reason = reason

        super().__init__(reason)
