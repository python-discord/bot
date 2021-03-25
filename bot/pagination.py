import asyncio
import logging
import typing as t
from contextlib import suppress

import discord
from discord import Member
from discord.abc import User
from discord.ext.commands import Context, Paginator

from bot import constants
from bot.constants import MODERATION_ROLES

FIRST_EMOJI = "\u23EE"   # [:track_previous:]
LEFT_EMOJI = "\u2B05"    # [:arrow_left:]
RIGHT_EMOJI = "\u27A1"   # [:arrow_right:]
LAST_EMOJI = "\u23ED"    # [:track_next:]
DELETE_EMOJI = constants.Emojis.trashcan  # [:trashcan:]

PAGINATION_EMOJI = (FIRST_EMOJI, LEFT_EMOJI, RIGHT_EMOJI, LAST_EMOJI, DELETE_EMOJI)

log = logging.getLogger(__name__)


class EmptyPaginatorEmbed(Exception):
    """Raised when attempting to paginate with empty contents."""

    pass


class LinePaginator(Paginator):
    """
    A class that aids in paginating code blocks for Discord messages.

    Available attributes include:
    * prefix: `str`
        The prefix inserted to every page. e.g. three backticks.
    * suffix: `str`
        The suffix appended at the end of every page. e.g. three backticks.
    * max_size: `int`
        The maximum amount of codepoints allowed in a page.
    * scale_to_size: `int`
        The maximum amount of characters a single line can scale up to.
    * max_lines: `int`
        The maximum amount of lines allowed in a page.
    """

    def __init__(
        self,
        prefix: str = '```',
        suffix: str = '```',
        max_size: int = 2000,
        scale_to_size: int = 2000,
        max_lines: t.Optional[int] = None
    ) -> None:
        """
        This function overrides the Paginator.__init__ from inside discord.ext.commands.

        It overrides in order to allow us to configure the maximum number of lines per page.
        """
        self.prefix = prefix
        self.suffix = suffix

        # Embeds that exceed 2048 characters will result in an HTTPException
        # (Discord API limit), so we've set a limit of 2000
        if max_size > 2000:
            raise ValueError(f"max_size must be <= 2,000 characters. ({max_size} > 2000)")

        self.max_size = max_size - len(suffix)

        if scale_to_size < max_size:
            raise ValueError(f"scale_to_size must be >= max_size. ({scale_to_size} < {max_size})")

        if scale_to_size > 2000:
            raise ValueError(f"scale_to_size must be <= 2,000 characters. ({scale_to_size} > 2000)")

        self.scale_to_size = scale_to_size - len(suffix)
        self.max_lines = max_lines
        self._current_page = [prefix]
        self._linecount = 0
        self._count = len(prefix) + 1  # prefix + newline
        self._pages = []

    def add_line(self, line: str = '', *, empty: bool = False) -> None:
        """
        Adds a line to the current page.

        If a line on a page exceeds `max_size` characters, then `max_size` will go up to
        `scale_to_size` for a single line before creating a new page for the overflow words. If it
        is still exceeded, the excess characters are stored and placed on the next pages unti
        there are none remaining (by word boundary). The line is truncated if `scale_to_size` is
        still exceeded after attempting to continue onto the next page.

        In the case that the page already contains one or more lines and the new lines would cause
        `max_size` to be exceeded, a new page is created. This is done in order to make a best
        effort to avoid breaking up single lines across pages, while keeping the total length of the
        page at a reasonable size.

        This function overrides the `Paginator.add_line` from inside `discord.ext.commands`.

        It overrides in order to allow us to configure the maximum number of lines per page.
        """
        remaining_words = None
        if len(line) > (max_chars := self.max_size - len(self.prefix) - 2):
            if len(line) > self.scale_to_size:
                line, remaining_words = self._split_remaining_words(line, max_chars)
                if len(line) > self.scale_to_size:
                    log.debug("Could not continue to next page, truncating line.")
                    line = line[:self.scale_to_size]

        # Check if we should start a new page or continue the line on the current one
        if self.max_lines is not None and self._linecount >= self.max_lines:
            log.debug("max_lines exceeded, creating new page.")
            self._new_page()
        elif self._count + len(line) + 1 > self.max_size and self._linecount > 0:
            log.debug("max_size exceeded on page with lines, creating new page.")
            self._new_page()

        self._linecount += 1

        self._count += len(line) + 1
        self._current_page.append(line)

        if empty:
            self._current_page.append('')
            self._count += 1

        # Start a new page if there were any overflow words
        if remaining_words:
            self._new_page()
            self.add_line(remaining_words)

    def _new_page(self) -> None:
        """
        Internal: start a new page for the paginator.

        This closes the current page and resets the counters for the new page's line count and
        character count.
        """
        self._linecount = 0
        self._count = len(self.prefix) + 1
        self.close_page()

    def _split_remaining_words(self, line: str, max_chars: int) -> t.Tuple[str, t.Optional[str]]:
        """
        Internal: split a line into two strings -- reduced_words and remaining_words.

        reduced_words: the remaining words in `line`, after attempting to remove all words that
            exceed `max_chars` (rounding down to the nearest word boundary).

        remaining_words: the words in `line` which exceed `max_chars`. This value is None if
            no words could be split from `line`.

        If there are any remaining_words, an ellipses is appended to reduced_words and a
        continuation header is inserted before remaining_words to visually communicate the line
        continuation.

        Return a tuple in the format (reduced_words, remaining_words).
        """
        reduced_words = []
        remaining_words = []

        # "(Continued)" is used on a line by itself to indicate the continuation of last page
        continuation_header = "(Continued)\n-----------\n"
        reduced_char_count = 0
        is_full = False

        for word in line.split(" "):
            if not is_full:
                if len(word) + reduced_char_count <= max_chars:
                    reduced_words.append(word)
                    reduced_char_count += len(word) + 1
                else:
                    # If reduced_words is empty, we were unable to split the words across pages
                    if not reduced_words:
                        return line, None
                    is_full = True
                    remaining_words.append(word)
            else:
                remaining_words.append(word)

        return (
            " ".join(reduced_words) + "..." if remaining_words else "",
            continuation_header + " ".join(remaining_words) if remaining_words else None
        )

    @classmethod
    async def paginate(
        cls,
        lines: t.List[str],
        ctx: Context,
        embed: discord.Embed,
        prefix: str = "",
        suffix: str = "",
        max_lines: t.Optional[int] = None,
        max_size: int = 500,
        scale_to_size: int = 2000,
        empty: bool = True,
        restrict_to_user: User = None,
        timeout: int = 300,
        footer_text: str = None,
        url: str = None,
        exception_on_empty_embed: bool = False,
    ) -> t.Optional[discord.Message]:
        """
        Use a paginator and set of reactions to provide pagination over a set of lines.

        The reactions are used to switch page, or to finish with pagination.

        When used, this will send a message using `ctx.send()` and apply a set of reactions to it. These reactions may
        be used to change page, or to remove pagination from the message.

        Pagination will also be removed automatically if no reaction is added for five minutes (300 seconds).

        The interaction will be limited to `restrict_to_user` (ctx.author by default) or
        to any user with a moderation role.

        Example:
        >>> embed = discord.Embed()
        >>> embed.set_author(name="Some Operation", url=url, icon_url=icon)
        >>> await LinePaginator.paginate([line for line in lines], ctx, embed)
        """
        def event_check(reaction_: discord.Reaction, user_: discord.Member) -> bool:
            """Make sure that this reaction is what we want to operate on."""
            no_restrictions = (
                # The reaction was by a whitelisted user
                user_.id == restrict_to_user.id
                # The reaction was by a moderator
                or isinstance(user_, Member) and any(role.id in MODERATION_ROLES for role in user_.roles)
            )

            return (
                # Conditions for a successful pagination:
                all((
                    # Reaction is on this message
                    reaction_.message.id == message.id,
                    # Reaction is one of the pagination emotes
                    str(reaction_.emoji) in PAGINATION_EMOJI,
                    # Reaction was not made by the Bot
                    user_.id != ctx.bot.user.id,
                    # There were no restrictions
                    no_restrictions
                ))
            )

        paginator = cls(prefix=prefix, suffix=suffix, max_size=max_size, max_lines=max_lines,
                        scale_to_size=scale_to_size)
        current_page = 0

        if not restrict_to_user:
            restrict_to_user = ctx.author

        if not lines:
            if exception_on_empty_embed:
                log.exception("Pagination asked for empty lines iterable")
                raise EmptyPaginatorEmbed("No lines to paginate")

            log.debug("No lines to add to paginator, adding '(nothing to display)' message")
            lines.append("(nothing to display)")

        for line in lines:
            try:
                paginator.add_line(line, empty=empty)
            except Exception:
                log.exception(f"Failed to add line to paginator: '{line}'")
                raise  # Should propagate
            else:
                log.trace(f"Added line to paginator: '{line}'")

        log.debug(f"Paginator created with {len(paginator.pages)} pages")

        embed.description = paginator.pages[current_page]

        if len(paginator.pages) <= 1:
            if footer_text:
                embed.set_footer(text=footer_text)
                log.trace(f"Setting embed footer to '{footer_text}'")

            if url:
                embed.url = url
                log.trace(f"Setting embed url to '{url}'")

            log.debug("There's less than two pages, so we won't paginate - sending single page on its own")
            return await ctx.send(embed=embed)
        else:
            if footer_text:
                embed.set_footer(text=f"{footer_text} (Page {current_page + 1}/{len(paginator.pages)})")
            else:
                embed.set_footer(text=f"Page {current_page + 1}/{len(paginator.pages)}")
            log.trace(f"Setting embed footer to '{embed.footer.text}'")

            if url:
                embed.url = url
                log.trace(f"Setting embed url to '{url}'")

            log.debug("Sending first page to channel...")
            message = await ctx.send(embed=embed)

        log.debug("Adding emoji reactions to message...")

        for emoji in PAGINATION_EMOJI:
            # Add all the applicable emoji to the message
            log.trace(f"Adding reaction: {repr(emoji)}")
            await message.add_reaction(emoji)

        while True:
            try:
                reaction, user = await ctx.bot.wait_for("reaction_add", timeout=timeout, check=event_check)
                log.trace(f"Got reaction: {reaction}")
            except asyncio.TimeoutError:
                log.debug("Timed out waiting for a reaction")
                break  # We're done, no reactions for the last 5 minutes

            if str(reaction.emoji) == DELETE_EMOJI:
                log.debug("Got delete reaction")
                return await message.delete()

            if reaction.emoji == FIRST_EMOJI:
                await message.remove_reaction(reaction.emoji, user)
                current_page = 0

                log.debug(f"Got first page reaction - changing to page 1/{len(paginator.pages)}")

                embed.description = paginator.pages[current_page]
                if footer_text:
                    embed.set_footer(text=f"{footer_text} (Page {current_page + 1}/{len(paginator.pages)})")
                else:
                    embed.set_footer(text=f"Page {current_page + 1}/{len(paginator.pages)}")
                await message.edit(embed=embed)

            if reaction.emoji == LAST_EMOJI:
                await message.remove_reaction(reaction.emoji, user)
                current_page = len(paginator.pages) - 1

                log.debug(f"Got last page reaction - changing to page {current_page + 1}/{len(paginator.pages)}")

                embed.description = paginator.pages[current_page]
                if footer_text:
                    embed.set_footer(text=f"{footer_text} (Page {current_page + 1}/{len(paginator.pages)})")
                else:
                    embed.set_footer(text=f"Page {current_page + 1}/{len(paginator.pages)}")
                await message.edit(embed=embed)

            if reaction.emoji == LEFT_EMOJI:
                await message.remove_reaction(reaction.emoji, user)

                if current_page <= 0:
                    log.debug("Got previous page reaction, but we're on the first page - ignoring")
                    continue

                current_page -= 1
                log.debug(f"Got previous page reaction - changing to page {current_page + 1}/{len(paginator.pages)}")

                embed.description = paginator.pages[current_page]

                if footer_text:
                    embed.set_footer(text=f"{footer_text} (Page {current_page + 1}/{len(paginator.pages)})")
                else:
                    embed.set_footer(text=f"Page {current_page + 1}/{len(paginator.pages)}")

                await message.edit(embed=embed)

            if reaction.emoji == RIGHT_EMOJI:
                await message.remove_reaction(reaction.emoji, user)

                if current_page >= len(paginator.pages) - 1:
                    log.debug("Got next page reaction, but we're on the last page - ignoring")
                    continue

                current_page += 1
                log.debug(f"Got next page reaction - changing to page {current_page + 1}/{len(paginator.pages)}")

                embed.description = paginator.pages[current_page]

                if footer_text:
                    embed.set_footer(text=f"{footer_text} (Page {current_page + 1}/{len(paginator.pages)})")
                else:
                    embed.set_footer(text=f"Page {current_page + 1}/{len(paginator.pages)}")

                await message.edit(embed=embed)

        log.debug("Ending pagination and clearing reactions.")
        with suppress(discord.NotFound):
            await message.clear_reactions()
