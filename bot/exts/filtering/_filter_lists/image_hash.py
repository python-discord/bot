import typing

import aiohttp
from pydis_core.utils.logging import get_logger

from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filter_lists.filter_list import FilterList, ListType
from bot.exts.filtering._filters.filter import Filter
from bot.exts.filtering._filters.image_hash import ImageHashFilter
from bot.exts.filtering._image_hash import RhodiumAPIError, get_image_hash
from bot.exts.filtering._settings import ActionSettings

if typing.TYPE_CHECKING:
    from bot.exts.filtering.filtering import Filtering

log = get_logger(__name__)

_MAX_IMAGE_SIZE = 5_000_000


class ImageHashesList(FilterList[ImageHashFilter]):
    """A list of perceptual image hashes that should trigger filtering when matched."""

    name = "image_hash"

    def __init__(self, filtering_cog: Filtering):
        super().__init__()
        filtering_cog.subscribe(self, Event.MESSAGE)

    def get_filter_type(self, content: str) -> type[Filter]:
        """Get a subclass of filter matching the filter list and the filter's content."""
        return ImageHashFilter

    @property
    def filter_types(self) -> set[type[Filter]]:
        """Return the types of filters used by this list."""
        return {ImageHashFilter}

    async def actions_for(
        self, ctx: FilterContext
    ) -> tuple[ActionSettings | None, list[str], dict[ListType, list[Filter]]]:
        """Dispatch the given event to the list's filters, and return actions to take and messages to relay to mods."""
        if not ctx.attachments:
            return None, [], {}

        image_hashes = []
        for attachment in ctx.attachments:
            if (
                attachment.content_type is None
                or not attachment.content_type.startswith("image")
                or attachment.size > _MAX_IMAGE_SIZE
            ):
                continue

            try:
                image_hash = await get_image_hash(attachment.url)
            except aiohttp.ClientError:
                log.exception("Unhandled aiohttp exception while getting image hash")
                continue
            except RhodiumAPIError as e:
                log.exception("Rhodium API error: %s", e)
                continue
            except TimeoutError:
                log.exception("Timed out getting image hash")
                continue

            image_hashes.append(image_hash)

        if not image_hashes:
            return None, [], {}

        trigger_ctx = ctx.replace(content=image_hashes)
        triggers = await self[ListType.DENY].filter_list_result(trigger_ctx)
        if not triggers:
            return None, [], {ListType.DENY: triggers}

        actions = self[ListType.DENY].merge_actions(triggers)
        messages = []
        for filter_ in triggers:
            distance = ctx.filter_info.get(filter_, "?")
            messages.append(
                f"{filter_.id} (`{filter_.content}` distance `{distance}`)"
                f" - {filter_.description or '*No description*'}"
            )
        return actions, messages, {ListType.DENY: triggers}
