from collections.abc import Sequence
import discord
from discord.ext.commands import Context
from pydis_core.utils.pagination import LinePaginator as _LinePaginator, PaginationEmojis
from bot.constants import Emojis

class LinePaginator(_LinePaginator):
    """
    A class that aids in paginating code blocks for Discord messages.
    Extends the functionality of the base LinePaginator class.
    """

    @classmethod
    async def paginate(
        cls,
        lines: list[str],
        ctx: Context | discord.Interaction,
        embed: discord.Embed,
        prefix: str = "",
        suffix: str = "",
        max_lines: int | None = None,
        max_size: int = 500,
        scale_to_size: int = 4000,
        empty: bool = True,
        restrict_to_user: discord.User | None = None,
        timeout: int = 300,
        footer_text: str | None = None,
        url: str | None = None,
        exception_on_empty_embed: bool = False,
        reply: bool = False,
        allowed_roles: Sequence[int] | None = None,
        **kwargs
    ) -> discord.Message | None:
        """
        Use a paginator and set of reactions to provide pagination over a set of lines.

        This method wraps the superclass's `paginate` method, providing custom pagination emojis by default.
        All parameters are passed directly to the superclass method.

        Returns:
            discord.Message | None: The message object if pagination is successful, None otherwise.
        """
        pagination_emojis = PaginationEmojis(delete=Emojis.trashcan)
        
        return await super().paginate(
            pagination_emojis=pagination_emojis,
            lines=lines,
            ctx=ctx,
            embed=embed,
            prefix=prefix,
            suffix=suffix,
            max_lines=max_lines,
            max_size=max_size,
            scale_to_size=scale_to_size,
            empty=empty,
            restrict_to_user=restrict_to_user,
            timeout=timeout,
            footer_text=footer_text,
            url=url,
            exception_on_empty_embed=exception_on_empty_embed,
            reply=reply,
            allowed_roles=allowed_roles,
            **kwargs
        )
