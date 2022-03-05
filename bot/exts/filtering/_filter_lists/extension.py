from __future__ import annotations

import typing
from os.path import splitext
from typing import Optional, Type

import bot
from bot.constants import Channels, URLs
from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filter_lists.filter_list import FilterList, ListType
from bot.exts.filtering._filters.extension import ExtensionFilter
from bot.exts.filtering._filters.filter import Filter
from bot.exts.filtering._settings import ActionSettings

if typing.TYPE_CHECKING:
    from bot.exts.filtering.filtering import Filtering


PY_EMBED_DESCRIPTION = (
    "It looks like you tried to attach a Python file - "
    f"please use a code-pasting service such as {URLs.site_schema}{URLs.site_paste}"
)

TXT_LIKE_FILES = {".txt", ".csv", ".json"}
TXT_EMBED_DESCRIPTION = (
    "You either uploaded a `{blocked_extension}` file or entered a message that was too long. "
    f"Please use our [paste bin]({URLs.site_schema}{URLs.site_paste}) instead."
)

DISALLOWED_EMBED_DESCRIPTION = (
    "It looks like you tried to attach file type(s) that we do not allow ({blocked_extensions_str}). "
    "We currently allow the following file types: **{joined_whitelist}**.\n\n"
    "Feel free to ask in {meta_channel_mention} if you think this is a mistake."
)


class ExtensionsList(FilterList):
    """
    A list of filters, each looking for a file attachment with a specific extension.

    If an extension is not explicitly allowed, it will be blocked.

    Whitelist defaults dictate what happens when an extension is *not* explicitly allowed,
    and whitelist filters overrides have no effect.

    Items should be added as file extensions preceded by a dot.
    """

    name = "extension"

    def __init__(self, filtering_cog: Filtering):
        super().__init__(ExtensionFilter)
        filtering_cog.subscribe(self, Event.MESSAGE)
        self._whitelisted_description = None

    @property
    def filter_types(self) -> set[Type[Filter]]:
        """Return the types of filters used by this list."""
        return {ExtensionFilter}

    async def actions_for(self, ctx: FilterContext) -> tuple[Optional[ActionSettings], Optional[str]]:
        """Dispatch the given event to the list's filters, and return actions to take and a message to relay to mods."""
        # Return early if the message doesn't have attachments.
        if not ctx.message.attachments:
            return None, ""

        _, failed = self.defaults[ListType.ALLOW]["validations"].evaluate(ctx)
        if failed:  # There's no extension filtering in this context.
            return None, ""

        # Find all extensions in the message.
        all_ext = {
            (splitext(attachment.filename.lower())[1], attachment.filename) for attachment in ctx.message.attachments
        }
        new_ctx = ctx.replace(content={ext for ext, _ in all_ext})  # And prepare the context for the filters to read.
        triggered = [filter_ for filter_ in self.filter_lists[ListType.ALLOW] if filter_.triggered_on(new_ctx)]
        allowed_ext = {filter_.content for filter_ in triggered}  # Get the extensions in the message that are allowed.

        # See if there are any extensions left which aren't allowed.
        not_allowed = {ext: filename for ext, filename in all_ext if ext not in allowed_ext}

        if not not_allowed:  # Yes, it's a double negative. Meaning all attachments are allowed :)
            return None, ""

        # Something is disallowed.
        if ".py" in not_allowed:
            # Provide a pastebin link for .py files.
            ctx.dm_embed = PY_EMBED_DESCRIPTION
        elif txt_extensions := {ext for ext in TXT_LIKE_FILES if ext in not_allowed}:
            # Work around Discord auto-conversion of messages longer than 2000 chars to .txt
            cmd_channel = bot.instance.get_channel(Channels.bot_commands)
            ctx.dm_embed = TXT_EMBED_DESCRIPTION.format(
                blocked_extension=txt_extensions.pop(),
                cmd_channel_mention=cmd_channel.mention
            )
        else:
            meta_channel = bot.instance.get_channel(Channels.meta)
            if not self._whitelisted_description:
                self._whitelisted_description = ', '.join(
                    filter_.content for filter_ in self.filter_lists[ListType.ALLOW]
                )
            ctx.dm_embed = DISALLOWED_EMBED_DESCRIPTION.format(
                joined_whitelist=self._whitelisted_description,
                blocked_extensions_str=", ".join(not_allowed),
                meta_channel_mention=meta_channel.mention,
            )

        ctx.matches += not_allowed.values()
        return self.defaults[ListType.ALLOW]["actions"], ", ".join(f"`{ext}`" for ext in not_allowed)
