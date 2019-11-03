import asyncio
import functools
import logging
import re
import textwrap
from collections import OrderedDict
from contextlib import suppress
from typing import Any, Callable, Optional, Tuple

import discord
from bs4 import BeautifulSoup
from bs4.element import PageElement, Tag
from discord.errors import NotFound
from discord.ext import commands
from markdownify import MarkdownConverter
from requests import ConnectTimeout, ConnectionError, HTTPError
from sphinx.ext import intersphinx
from urllib3.exceptions import ProtocolError

from bot.constants import MODERATION_ROLES, RedirectOutput
from bot.converters import ValidPythonIdentifier, ValidURL
from bot.decorators import with_role
from bot.pagination import LinePaginator


log = logging.getLogger(__name__)
logging.getLogger('urllib3').setLevel(logging.WARNING)

NOT_FOUND_DELETE_DELAY = RedirectOutput.delete_delay
NO_OVERRIDE_GROUPS = (
    "2to3fixer",
    "token",
    "label",
    "pdbcommand",
    "term",
)
NO_OVERRIDE_PACKAGES = (
    "Python",
)
FAILED_REQUEST_RETRY_AMOUNT = 3
UNWANTED_SIGNATURE_SYMBOLS_RE = re.compile(r"\[source]|\\\\|¶")
SEARCH_END_TAG_ATTRS = (
    "data",
    "function",
    "class",
    "exception",
    "seealso",
    "section",
    "rubric",
    "sphinxsidebar",
)
WHITESPACE_AFTER_NEWLINES_RE = re.compile(r"(?<=\n\n)(\s+)")


def async_cache(max_size: int = 128, arg_offset: int = 0) -> Callable:
    """
    LRU cache implementation for coroutines.

    Once the cache exceeds the maximum size, keys are deleted in FIFO order.

    An offset may be optionally provided to be applied to the coroutine's arguments when creating the cache key.
    """
    # Assign the cache to the function itself so we can clear it from outside.
    async_cache.cache = OrderedDict()

    def decorator(function: Callable) -> Callable:
        """Define the async_cache decorator."""
        @functools.wraps(function)
        async def wrapper(*args) -> Any:
            """Decorator wrapper for the caching logic."""
            key = ':'.join(args[arg_offset:])

            value = async_cache.cache.get(key)
            if value is None:
                if len(async_cache.cache) > max_size:
                    async_cache.cache.popitem(last=False)

                async_cache.cache[key] = await function(*args)
            return async_cache.cache[key]
        return wrapper
    return decorator


class DocMarkdownConverter(MarkdownConverter):
    """Subclass markdownify's MarkdownCoverter to provide custom conversion methods."""

    def convert_code(self, el: PageElement, text: str) -> str:
        """Undo `markdownify`s underscore escaping."""
        return f"`{text}`".replace('\\', '')

    def convert_pre(self, el: PageElement, text: str) -> str:
        """Wrap any codeblocks in `py` for syntax highlighting."""
        code = ''.join(el.strings)
        return f"```py\n{code}```"


def markdownify(html: str) -> DocMarkdownConverter:
    """Create a DocMarkdownConverter object from the input html."""
    return DocMarkdownConverter(bullets='•').convert(html)


class DummyObject(object):
    """A dummy object which supports assigning anything, which the builtin `object()` does not support normally."""


class SphinxConfiguration:
    """Dummy configuration for use with intersphinx."""

    config = DummyObject()
    config.intersphinx_timeout = 3
    config.tls_verify = True


class InventoryURL(commands.Converter):
    """
    Represents an Intersphinx inventory URL.

    This converter checks whether intersphinx accepts the given inventory URL, and raises
    `BadArgument` if that is not the case.

    Otherwise, it simply passes through the given URL.
    """

    @staticmethod
    async def convert(ctx: commands.Context, url: str) -> str:
        """Convert url to Intersphinx inventory URL."""
        try:
            intersphinx.fetch_inventory(SphinxConfiguration(), '', url)
        except AttributeError:
            raise commands.BadArgument(f"Failed to fetch Intersphinx inventory from URL `{url}`.")
        except ConnectionError:
            if url.startswith('https'):
                raise commands.BadArgument(
                    f"Cannot establish a connection to `{url}`. Does it support HTTPS?"
                )
            raise commands.BadArgument(f"Cannot connect to host with URL `{url}`.")
        except ValueError:
            raise commands.BadArgument(
                f"Failed to read Intersphinx inventory from URL `{url}`. "
                "Are you sure that it's a valid inventory file?"
            )
        return url


class Doc(commands.Cog):
    """A set of commands for querying & displaying documentation."""

    def __init__(self, bot: commands.Bot):
        self.base_urls = {}
        self.bot = bot
        self.inventories = {}
        self.renamed_symbols = set()

        self.bot.loop.create_task(self.init_refresh_inventory())

    async def init_refresh_inventory(self) -> None:
        """Refresh documentation inventory on cog initialization."""
        await self.bot.wait_until_ready()
        await self.refresh_inventory()

    async def update_single(
        self, package_name: str, base_url: str, inventory_url: str, config: SphinxConfiguration
    ) -> None:
        """
        Rebuild the inventory for a single package.

        Where:
            * `package_name` is the package name to use, appears in the log
            * `base_url` is the root documentation URL for the specified package, used to build
                absolute paths that link to specific symbols
            * `inventory_url` is the absolute URL to the intersphinx inventory, fetched by running
                `intersphinx.fetch_inventory` in an executor on the bot's event loop
            * `config` is a `SphinxConfiguration` instance to mock the regular sphinx
                project layout, required for use with intersphinx
        """
        self.base_urls[package_name] = base_url

        package = await self._fetch_inventory(inventory_url, config)
        if package:
            for group, value in package.items():
                # Each value has a bunch of information in the form
                # `(package_name, version, relative_url, ???)`, and we only
                # need the package_name and the relative documentation URL.
                for symbol, (package_name, _, relative_doc_url, _) in value.items():
                    absolute_doc_url = base_url + relative_doc_url

                    if symbol in self.inventories:
                        # get `group_name` from _:group_name
                        group_name = group.split(":")[1]
                        if (group_name in NO_OVERRIDE_GROUPS
                                # check if any package from `NO_OVERRIDE_PACKAGES`
                                # is in base URL of the symbol that would be overridden
                                or any(package in self.inventories[symbol].split("/", 3)[2]
                                       for package in NO_OVERRIDE_PACKAGES)):

                            symbol = f"{group_name}.{symbol}"
                            # if renamed `symbol` was already exists, add library name in front
                            if symbol in self.renamed_symbols:
                                # split `package_name` because of packages like Pillow that have spaces in them
                                symbol = f"{package_name.split()[0]}.{symbol}"

                            self.inventories[symbol] = absolute_doc_url
                            self.renamed_symbols.add(symbol)
                            continue

                    self.inventories[symbol] = absolute_doc_url

            log.trace(f"Fetched inventory for {package_name}.")

    async def refresh_inventory(self) -> None:
        """Refresh internal documentation inventory."""
        log.debug("Refreshing documentation inventory...")

        # Clear the old base URLS and inventories to ensure
        # that we start from a fresh local dataset.
        # Also, reset the cache used for fetching documentation.
        self.base_urls.clear()
        self.inventories.clear()
        async_cache.cache = OrderedDict()

        # Since Intersphinx is intended to be used with Sphinx,
        # we need to mock its configuration.
        config = SphinxConfiguration()

        # Run all coroutines concurrently - since each of them performs a HTTP
        # request, this speeds up fetching the inventory data heavily.
        coros = [
            self.update_single(
                package["package"], package["base_url"], package["inventory_url"], config
            ) for package in await self.bot.api_client.get('bot/documentation-links')
        ]
        await asyncio.gather(*coros)

    async def get_symbol_html(self, symbol: str) -> Optional[Tuple[list, str]]:
        """
        Given a Python symbol, return its signature and description.

        The first tuple element is the signature of the given symbol as a markup-free string, and
        the second tuple element is the description of the given symbol with HTML markup included.

        If the given symbol is a module, returns a tuple `(None, str)`
        else if the symbol could not be found, returns `None`.
        """
        url = self.inventories.get(symbol)
        if url is None:
            return None

        async with self.bot.http_session.get(url) as response:
            html = await response.text(encoding='utf-8')

        # Find the signature header and parse the relevant parts.
        symbol_id = url.split('#')[-1]
        soup = BeautifulSoup(html, 'lxml')
        symbol_heading = soup.find(id=symbol_id)
        signatures = []

        if symbol_heading is None:
            return None

        if symbol_id == f"module-{symbol}":
            search_html = str(soup)
            # Get page content from the module headerlink to the
            # first tag that has its class in `SEARCH_END_TAG_ATTRS`
            start_tag = symbol_heading.find("a", attrs={"class": "headerlink"})
            if start_tag is None:
                return [], ""

            end_tag = start_tag.find_next(self._match_end_tag)
            if end_tag is None:
                return [], ""

            description_start_index = search_html.find(str(start_tag.parent)) + len(str(start_tag.parent))
            description_end_index = search_html.find(str(end_tag))
            description = search_html[description_start_index:description_end_index].replace('¶', '')
            signatures = None

        else:
            # Get text of up to 3 signatures, remove unwanted symbols
            for element in [symbol_heading] + symbol_heading.find_next_siblings("dt", limit=2):
                signature = UNWANTED_SIGNATURE_SYMBOLS_RE.sub("", element.text)
                if signature:
                    signatures.append(signature)
            description = str(symbol_heading.find_next_sibling("dd")).replace('¶', '')

        return signatures, description

    @async_cache(arg_offset=1)
    async def get_symbol_embed(self, symbol: str) -> Optional[discord.Embed]:
        """
        Attempt to scrape and fetch the data for the given `symbol`, and build an embed from its contents.

        If the symbol is known, an Embed with documentation about it is returned.
        """
        scraped_html = await self.get_symbol_html(symbol)
        if scraped_html is None:
            return None

        signatures = scraped_html[0]
        permalink = self.inventories[symbol]
        description = markdownify(scraped_html[1])

        # Truncate the description of the embed to the last occurrence
        # of a double newline (interpreted as a paragraph) before index 1000.
        if len(description) > 1000:
            shortened = description[:1000]
            last_paragraph_end = shortened.rfind('\n\n')
            description = description[:last_paragraph_end]

            # If there is an incomplete code block, cut it out
            if description.count("```") % 2:
                codeblock_start = description.rfind('```py')
                description = description[:codeblock_start].rstrip()
            description += f"... [read more]({permalink})"

        description = WHITESPACE_AFTER_NEWLINES_RE.sub('', description)

        if signatures is None:
            # If symbol is a module, don't show signature.
            embed_description = description

        elif not signatures:
            # It's some "meta-page", for example:
            # https://docs.djangoproject.com/en/dev/ref/views/#module-django.views
            embed_description = "This appears to be a generic page not tied to a specific symbol."

        else:
            embed_description = "".join(f"```py\n{textwrap.shorten(signature, 500)}```" for signature in signatures)
            embed_description += description

        embed = discord.Embed(
            title=f'`{symbol}`',
            url=permalink,
            description=embed_description
        )
        # Show all symbols with the same name that were renamed in the footer.
        embed.set_footer(text=", ".join(renamed for renamed in self.renamed_symbols - {symbol}
                                        if renamed.endswith(f".{symbol}"))
                         )
        return embed

    @commands.group(name='docs', aliases=('doc', 'd'), invoke_without_command=True)
    async def docs_group(self, ctx: commands.Context, symbol: commands.clean_content = None) -> None:
        """Lookup documentation for Python symbols."""
        await ctx.invoke(self.get_command, symbol)

    @docs_group.command(name='get', aliases=('g',))
    async def get_command(self, ctx: commands.Context, symbol: commands.clean_content = None) -> None:
        """
        Return a documentation embed for a given symbol.

        If no symbol is given, return a list of all available inventories.

        Examples:
            !docs
            !docs aiohttp
            !docs aiohttp.ClientSession
            !docs get aiohttp.ClientSession
        """
        if symbol is None:
            inventory_embed = discord.Embed(
                title=f"All inventories (`{len(self.base_urls)}` total)",
                colour=discord.Colour.blue()
            )

            lines = sorted(f"• [`{name}`]({url})" for name, url in self.base_urls.items())
            if self.base_urls:
                await LinePaginator.paginate(lines, ctx, inventory_embed, max_size=400, empty=False)

            else:
                inventory_embed.description = "Hmmm, seems like there's nothing here yet."
                await ctx.send(embed=inventory_embed)

        else:
            # Fetching documentation for a symbol (at least for the first time, since
            # caching is used) takes quite some time, so let's send typing to indicate
            # that we got the command, but are still working on it.
            async with ctx.typing():
                doc_embed = await self.get_symbol_embed(symbol)

            if doc_embed is None:
                error_embed = discord.Embed(
                    description=f"Sorry, I could not find any documentation for `{symbol}`.",
                    colour=discord.Colour.red()
                )
                error_message = await ctx.send(embed=error_embed)
                with suppress(NotFound):
                    await error_message.delete(delay=NOT_FOUND_DELETE_DELAY)
                    await ctx.message.delete(delay=NOT_FOUND_DELETE_DELAY)
            else:
                await ctx.send(embed=doc_embed)

    @docs_group.command(name='set', aliases=('s',))
    @with_role(*MODERATION_ROLES)
    async def set_command(
        self, ctx: commands.Context, package_name: ValidPythonIdentifier,
        base_url: ValidURL, inventory_url: InventoryURL
    ) -> None:
        """
        Adds a new documentation metadata object to the site's database.

        The database will update the object, should an existing item with the specified `package_name` already exist.

        Example:
            !docs set \
                    python \
                    https://docs.python.org/3/ \
                    https://docs.python.org/3/objects.inv
        """
        body = {
            'package': package_name,
            'base_url': base_url,
            'inventory_url': inventory_url
        }
        await self.bot.api_client.post('bot/documentation-links', json=body)

        log.info(
            f"User @{ctx.author.name}#{ctx.author.discriminator} ({ctx.author.id}) "
            "added a new documentation package:\n"
            f"Package name: {package_name}\n"
            f"Base url: {base_url}\n"
            f"Inventory URL: {inventory_url}"
        )

        # Rebuilding the inventory can take some time, so lets send out a
        # typing event to show that the Bot is still working.
        async with ctx.typing():
            await self.refresh_inventory()
        await ctx.send(f"Added package `{package_name}` to database and refreshed inventory.")

    @docs_group.command(name='delete', aliases=('remove', 'rm', 'd'))
    @with_role(*MODERATION_ROLES)
    async def delete_command(self, ctx: commands.Context, package_name: ValidPythonIdentifier) -> None:
        """
        Removes the specified package from the database.

        Examples:
            !docs delete aiohttp
        """
        await self.bot.api_client.delete(f'bot/documentation-links/{package_name}')

        async with ctx.typing():
            # Rebuild the inventory to ensure that everything
            # that was from this package is properly deleted.
            await self.refresh_inventory()
        await ctx.send(f"Successfully deleted `{package_name}` and refreshed inventory.")

    async def _fetch_inventory(self, inventory_url: str, config: SphinxConfiguration) -> Optional[dict]:
        """Get and return inventory from `inventory_url`. If fetching fails, return None."""
        fetch_func = functools.partial(intersphinx.fetch_inventory, config, '', inventory_url)
        for retry in range(1, FAILED_REQUEST_RETRY_AMOUNT+1):
            try:
                package = await self.bot.loop.run_in_executor(None, fetch_func)
            except ConnectTimeout:
                log.error(f"Fetching of inventory {inventory_url} timed out,"
                          f" trying again. ({retry}/{FAILED_REQUEST_RETRY_AMOUNT})")
            except ProtocolError:
                log.error(f"Connection lost while fetching inventory {inventory_url},"
                          f" trying again. ({retry}/{FAILED_REQUEST_RETRY_AMOUNT})")
            except HTTPError as e:
                log.error(f"Fetching of inventory {inventory_url} failed with status code {e.response.status_code}.")
                return None
            except ConnectionError:
                log.error(f"Couldn't establish connection to inventory {inventory_url}.")
                return None
            else:
                return package
        log.error(f"Fetching of inventory {inventory_url} failed.")
        return None

    @staticmethod
    def _match_end_tag(tag: Tag) -> bool:
        """Matches `tag` if its class value is in `SEARCH_END_TAG_ATTRS` or the tag is table."""
        for attr in SEARCH_END_TAG_ATTRS:
            if attr in tag.get("class", ()):
                return True

        return tag.name == "table"


def setup(bot: commands.Bot) -> None:
    """Doc cog load."""
    bot.add_cog(Doc(bot))
    log.info("Cog loaded: Doc")
