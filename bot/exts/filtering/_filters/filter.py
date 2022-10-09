from abc import abstractmethod
from typing import Optional

from pydantic import ValidationError

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings import create_settings
from bot.exts.filtering._utils import FieldRequiring


class Filter(FieldRequiring):
    """
    A class representing a filter.

    Each filter looks for a specific attribute within an event (such as message sent),
    and defines what action should be performed if it is triggered.
    """

    # Each subclass must define a name which will be used to fetch its description.
    # Names must be unique across all types of filters.
    name = FieldRequiring.MUST_SET_UNIQUE
    # If a subclass uses extra fields, it should assign the pydantic model type to this variable.
    extra_fields_type = None

    def __init__(self, filter_data: dict):
        self.id = filter_data["id"]
        self.content = filter_data["content"]
        self.description = filter_data["description"]
        self.actions, self.validations = create_settings(filter_data["settings"])
        self.extra_fields = filter_data["additional_field"] or "{}"  # noqa: P103
        if self.extra_fields_type:
            self.extra_fields = self.extra_fields_type.parse_raw(self.extra_fields)

    @abstractmethod
    def triggered_on(self, ctx: FilterContext) -> bool:
        """Search for the filter's content within a given context."""

    @classmethod
    def validate_filter_settings(cls, extra_fields: dict) -> tuple[bool, Optional[str]]:
        """Validate whether the supplied fields are valid for the filter, and provide the error message if not."""
        if cls.extra_fields_type is None:
            return True, None

        try:
            cls.extra_fields_type(**extra_fields)
        except ValidationError as e:
            return False, repr(e)
        else:
            return True, None

    @classmethod
    async def process_content(cls, content: str) -> str:
        """
        Process the content into a form which will work with the filtering.

        A ValueError should be raised if the content can't be used.
        """
        return content

    def __str__(self) -> str:
        """A string representation of the filter."""
        string = f"#{self.id}. `{self.content}`"
        if self.description:
            string += f" - {self.description}"
        return string