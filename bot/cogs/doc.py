import asyncio
import functools
import logging
import re
import textwrap
from collections import OrderedDict
from contextlib import suppress
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple, Union
from urllib.parse import urljoin

import discord
from bs4 import BeautifulSoup
from bs4.element import PageElement, Tag
from discord.errors import NotFound
from discord.ext import commands
from markdownify import MarkdownConverter
from requests import ConnectTimeout, ConnectionError, HTTPError
from sphinx.ext import intersphinx
from urllib3.exceptions import ProtocolError

from bot.bot import Bot
from bot.constants import MODERATION_ROLES, RedirectOutput
from bot.converters import ValidPythonIdentifier, ValidURL
from bot.decorators import with_role
from bot.pagination import LinePaginator


log = logging.getLogger(__name__)
logging.getLogger('urllib3').setLevel(logging.WARNING)

# Since Intersphinx is intended to be used with Sphinx,
# we need to mock its configuration.
SPHINX_MOCK_APP = SimpleNamespace(
    config=SimpleNamespace(
        intersphinx_timeout=3,
        tls_verify=True,
        user_agent="python3:python-discord/bot:1.0.0"
    )
)

NO_OVERRIDE_GROUPS = (
    "2to3fixer",
    "token",
    "label",
    "pdbcommand",
    "term",
)
NO_OVERRIDE_PACKAGES = (
    "python",
)

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
UNWANTED_SIGNATURE_SYMBOLS_RE = re.compile(r"\[source]|\\\\|¶")
WHITESPACE_AFTER_NEWLINES_RE = re.compile(r"(?<=\n\n)(\s+)")

FAILED_REQUEST_RETRY_AMOUNT = 3
NOT_FOUND_DELETE_DELAY = RedirectOutput.delete_delay


class DocItem(NamedTuple):
    """Holds inventory symbol information."""

    package: str
    url: str
    group: str


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

    def __init__(self, *, page_url: str, **options):
        super().__init__(**options)
        self.page_url = page_url

    def convert_code(self, el: PageElement, text: str) -> str:
        """Undo `markdownify`s underscore escaping."""
        return f"`{text}`".replace('\\', '')

    def convert_pre(self, el: PageElement, text: str) -> str:
        """Wrap any codeblocks in `py` for syntax highlighting."""
        code = ''.join(el.strings)
        return f"```py\n{code}```"

    def convert_a(self, el: PageElement, text: str) -> str:
        """Resolve relative URLs to `self.page_url`."""
        el["href"] = urljoin(self.page_url, el["href"])
        return super().convert_a(el, text)

    def convert_p(self, el: PageElement, text: str) -> str:
        """Include only one newline instead of two when the parent is a li tag."""
        parent = el.parent
        if parent is not None and parent.name == "li":
            return f"{text}\n"
        return super().convert_p(el, text)


def markdownify(html: str, *, url: str = "") -> str:
    """Create a DocMarkdownConverter object from the input html."""
    return DocMarkdownConverter(bullets='•', page_url=url).convert(html)


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
        await ctx.trigger_typing()
        try:
            intersphinx.fetch_inventory(SPHINX_MOCK_APP, '', url)
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

    def __init__(self, bot: Bot):
        self.base_urls = {}
        self.bot = bot
        self.inventories: Dict[str, DocItem] = {}
        self.renamed_symbols = set()

        self.bot.loop.create_task(self.init_refresh_inventory())

    async def init_refresh_inventory(self) -> None:
        """Refresh documentation inventory on cog initialization."""
        await self.bot.wait_until_guild_available()
        await self.refresh_inventory()

    async def update_single(
        self, api_package_name: str, base_url: str, inventory_url: str
    ) -> None:
        """
        Rebuild the inventory for a single package.

        Where:
            * `package_name` is the package name to use, appears in the log
            * `base_url` is the root documentation URL for the specified package, used to build
                absolute paths that link to specific symbols
            * `inventory_url` is the absolute URL to the intersphinx inventory, fetched by running
                `intersphinx.fetch_inventory` in an executor on the bot's event loop
        """
        self.base_urls[api_package_name] = base_url

        package = await self._fetch_inventory(inventory_url)
        if not package:
            return None

        for group, value in package.items():
            for symbol, (_package_name, _version, relative_doc_url, _) in value.items():
                if "/" in symbol:
                    continue  # skip unreachable symbols with slashes
                absolute_doc_url = base_url + relative_doc_url
                group_name = group.split(":")[1]

                if symbol in self.inventories:
                    symbol_base_url = self.inventories[symbol].url.split("/", 3)[2]
                    if (
                        group_name in NO_OVERRIDE_GROUPS
                        or any(package in symbol_base_url for package in NO_OVERRIDE_PACKAGES)
                    ):
                        symbol = f"{group_name}.{symbol}"

                    elif (overridden_symbol_group := self.inventories[symbol].group) in NO_OVERRIDE_GROUPS:
                        overridden_symbol = f"{overridden_symbol_group}.{symbol}"
                        if overridden_symbol in self.renamed_symbols:
                            overridden_symbol = f"{api_package_name}.{overridden_symbol}"

                        self.inventories[overridden_symbol] = self.inventories[symbol]
                        self.renamed_symbols.add(overridden_symbol)

                    # If renamed `symbol` already exists, add library name in front to differentiate between them.
                    if symbol in self.renamed_symbols:
                        # Split `package_name` because of packages like Pillow that have spaces in them.
                        symbol = f"{api_package_name}.{symbol}"
                        self.renamed_symbols.add(symbol)

                self.inventories[symbol] = DocItem(api_package_name, absolute_doc_url, group_name)

        log.trace(f"Fetched inventory for {api_package_name}.")

    async def refresh_inventory(self) -> None:
        """Refresh internal documentation inventory."""
        log.debug("Refreshing documentation inventory...")

        # Clear the old base URLS and inventories to ensure
        # that we start from a fresh local dataset.
        # Also, reset the cache used for fetching documentation.
        self.base_urls.clear()
        self.inventories.clear()
        self.renamed_symbols.clear()
        async_cache.cache = OrderedDict()

        # Run all coroutines concurrently - since each of them performs a HTTP
        # request, this speeds up fetching the inventory data heavily.
        coros = [
            self.update_single(
                package["package"], package["base_url"], package["inventory_url"]
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
        symbol_info = self.inventories.get(symbol)
        if symbol_info is None:
            return None

        async with self.bot.http_session.get(symbol_info.url) as response:
            html = await response.text(encoding='utf-8')

        # Find the signature header and parse the relevant parts.
        symbol_id = symbol_info.url.split('#')[-1]
        soup = BeautifulSoup(html, 'lxml')
        symbol_heading = soup.find(id=symbol_id)
        search_html = str(soup)

        if symbol_heading is None:
            return None

        if symbol_id == f"module-{symbol}":
            parsed_module = self.parse_module_symbol(symbol_heading)
            if parsed_module is None:
                return [], ""
            else:
                signatures, description = parsed_module

        else:
            signatures, description = self.parse_symbol(symbol_heading, search_html)

        return signatures, description.replace('¶', '')

    @async_cache(arg_offset=1)
    async def get_symbol_embed(self, symbol: str) -> Optional[discord.Embed]:
        """
        Attempt to scrape and fetch the data for the given `symbol`, and build an embed from its contents.

        If the symbol is known, an Embed with documentation about it is returned.
        """
        scraped_html = await self.get_symbol_html(symbol)
        if scraped_html is None:
            return None

        symbol_obj = self.inventories[symbol]
        self.bot.stats.incr(f"doc_fetches.{symbol_obj.package.lower()}")
        signatures = scraped_html[0]
        permalink = symbol_obj.url
        description = markdownify(scraped_html[1], url=permalink)

        # Truncate the description of the embed to the last occurrence
        # of a double newline (interpreted as a paragraph) before index 1000.
        if len(description) > 1000:
            shortened = description[:1000]
            description_cutoff = shortened.rfind('\n\n', 100)
            if description_cutoff == -1:
                # Search the shortened version for cutoff points in decreasing desirability,
                # cutoff at 1000 if none are found.
                for string in (". ", ", ", ",", " "):
                    description_cutoff = shortened.rfind(string)
                    if description_cutoff != -1:
                        break
                else:
                    description_cutoff = 1000
            description = description[:description_cutoff]

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
            embed_description += f"\n{description}"

        embed = discord.Embed(
            title=f'`{symbol}`',
            url=permalink,
            description=embed_description
        )
        # Show all symbols with the same name that were renamed in the footer.
        embed.set_footer(
            text=", ".join(renamed for renamed in self.renamed_symbols - {symbol} if renamed.endswith(f".{symbol}"))
        )
        return embed

    @classmethod
    def parse_module_symbol(cls, heading: PageElement) -> Optional[Tuple[None, str]]:
        """Get page content from the headerlink up to a table or a tag with its class in `SEARCH_END_TAG_ATTRS`."""
        start_tag = heading.find("a", attrs={"class": "headerlink"})
        if start_tag is None:
            return None

        description = cls.find_all_children_until_tag(start_tag, cls._match_end_tag)
        if description is None:
            return None

        return None, description

    @classmethod
    def parse_symbol(cls, heading: PageElement, html: str) -> Tuple[List[str], str]:
        """
        Parse the signatures and description of a symbol.

        Collects up to 3 signatures from dt tags and a description from their sibling dd tag.
        """
        signatures = []
        description_element = heading.find_next_sibling("dd")
        description_pos = html.find(str(description_element))
        description = cls.find_all_children_until_tag(description_element, tag_filter=("dt", "dl"))

        for element in (
            *reversed(heading.find_previous_siblings("dt", limit=2)),
            heading,
            *heading.find_next_siblings("dt", limit=2),
        )[-3:]:
            signature = UNWANTED_SIGNATURE_SYMBOLS_RE.sub("", element.text)

            if signature and html.find(str(element)) < description_pos:
                signatures.append(signature)

        return signatures, description

    @staticmethod
    def find_all_children_until_tag(
            start_element: PageElement,
            tag_filter: Union[Tuple[str, ...], Callable[[Tag], bool]]
    ) -> Optional[str]:
        """
        Get all direct children until a child matching `tag_filter` is found.

        `tag_filter` can be either a tuple of string names to check against,
        or a filtering callable that's applied to the tags.
        """
        text = ""

        for element in start_element.find_next().find_next_siblings():
            if isinstance(tag_filter, tuple):
                if element.name in tag_filter:
                    break
            elif tag_filter(element):
                break
            text += str(element)

        return text

    @commands.group(name='docs', aliases=('doc', 'd'), invoke_without_command=True)
    async def docs_group(self, ctx: commands.Context, *, symbol: str) -> None:
        """Lookup documentation for Python symbols."""
        await ctx.invoke(self.get_command, symbol=symbol)

    @docs_group.command(name='get', aliases=('g',))
    async def get_command(self, ctx: commands.Context, *, symbol: str) -> None:
        """
        Return a documentation embed for a given symbol.

        If no symbol is given, return a list of all available inventories.

        Examples:
            !docs
            !docs aiohttp
            !docs aiohttp.ClientSession
            !docs get aiohttp.ClientSession
        """
        if not symbol:
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
            symbol = symbol.strip("`")
            # Fetching documentation for a symbol (at least for the first time, since
            # caching is used) takes quite some time, so let's send typing to indicate
            # that we got the command, but are still working on it.
            async with ctx.typing():
                doc_embed = await self.get_symbol_embed(symbol)

            if doc_embed is None:
                symbol = await discord.ext.commands.clean_content().convert(ctx, symbol)
                error_embed = discord.Embed(
                    description=f"Sorry, I could not find any documentation for `{(symbol)}`.",
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
            f"User @{ctx.author} ({ctx.author.id}) added a new documentation package:\n"
            f"Package name: {package_name}\n"
            f"Base url: {base_url}\n"
            f"Inventory URL: {inventory_url}"
        )

        await self.update_single(package_name, base_url, inventory_url)
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

    @docs_group.command(name="refresh", aliases=("rfsh", "r"))
    @with_role(*MODERATION_ROLES)
    async def refresh_command(self, ctx: commands.Context) -> None:
        """Refresh inventories and send differences to channel."""
        old_inventories = set(self.base_urls)
        with ctx.typing():
            await self.refresh_inventory()
        new_inventories = set(self.base_urls)

        if added := ", ".join(new_inventories - old_inventories):
            added = "+ " + added

        if removed := ", ".join(old_inventories - new_inventories):
            removed = "- " + removed

        embed = discord.Embed(
            title="Inventories refreshed",
            description=f"```diff\n{added}\n{removed}```" if added or removed else ""
        )
        await ctx.send(embed=embed)

    async def _fetch_inventory(self, inventory_url: str) -> Optional[dict]:
        """Get and return inventory from `inventory_url`. If fetching fails, return None."""
        fetch_func = functools.partial(intersphinx.fetch_inventory, SPHINX_MOCK_APP, '', inventory_url)
        for retry in range(1, FAILED_REQUEST_RETRY_AMOUNT+1):
            try:
                package = await self.bot.loop.run_in_executor(None, fetch_func)
            except ConnectTimeout:
                log.error(
                    f"Fetching of inventory {inventory_url} timed out,"
                    f" trying again. ({retry}/{FAILED_REQUEST_RETRY_AMOUNT})"
                )
            except ProtocolError:
                log.error(
                    f"Connection lost while fetching inventory {inventory_url},"
                    f" trying again. ({retry}/{FAILED_REQUEST_RETRY_AMOUNT})"
                )
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


def setup(bot: Bot) -> None:
    """Load the Doc cog."""
    bot.add_cog(Doc(bot))
