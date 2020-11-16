import asyncio
import functools
import logging
import re
import textwrap
from contextlib import suppress
from types import SimpleNamespace
from typing import Optional, Tuple

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
from bot.pagination import LinePaginator
from bot.utils.cache import AsyncCache
from bot.utils.messages import wait_for_deletion


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

symbol_cache = AsyncCache()


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
        self.inventories = {}
        self.renamed_symbols = set()

        self.bot.loop.create_task(self.init_refresh_inventory())

    async def init_refresh_inventory(self) -> None:
        """Refresh documentation inventory on cog initialization."""
        await self.bot.wait_until_guild_available()
        await self.refresh_inventory()

    async def update_single(
        self, package_name: str, base_url: str, inventory_url: str
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
        self.base_urls[package_name] = base_url

        package = await self._fetch_inventory(inventory_url)
        if not package:
            return None

        for group, value in package.items():
            for symbol, (package_name, _version, relative_doc_url, _) in value.items():
                absolute_doc_url = base_url + relative_doc_url

                if symbol in self.inventories:
                    group_name = group.split(":")[1]
                    symbol_base_url = self.inventories[symbol].split("/", 3)[2]
                    if (
                        group_name in NO_OVERRIDE_GROUPS
                        or any(package in symbol_base_url for package in NO_OVERRIDE_PACKAGES)
                    ):

                        symbol = f"{group_name}.{symbol}"
                        # If renamed `symbol` already exists, add library name in front to differentiate between them.
                        if symbol in self.renamed_symbols:
                            # Split `package_name` because of packages like Pillow that have spaces in them.
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
        self.renamed_symbols.clear()
        symbol_cache.clear()

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
        url = self.inventories.get(symbol)
        if url is None:
            return None

        async with self.bot.http_session.get(url) as response:
            html = await response.text(encoding='utf-8')

        # Find the signature header and parse the relevant parts.
        symbol_id = url.split('#')[-1]
        soup = BeautifulSoup(html, 'lxml')
        symbol_heading = soup.find(id=symbol_id)
        search_html = str(soup)

        if symbol_heading is None:
            return None

        if symbol_id == f"module-{symbol}":
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
            description = search_html[description_start_index:description_end_index]
            signatures = None

        else:
            signatures = []
            description = str(symbol_heading.find_next_sibling("dd"))
            description_pos = search_html.find(description)
            # Get text of up to 3 signatures, remove unwanted symbols
            for element in [symbol_heading] + symbol_heading.find_next_siblings("dt", limit=2):
                signature = UNWANTED_SIGNATURE_SYMBOLS_RE.sub("", element.text)
                if signature and search_html.find(str(element)) < description_pos:
                    signatures.append(signature)

        return signatures, description.replace('¶', '')

    @symbol_cache(arg_offset=1)
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

    @commands.group(name='docs', aliases=('doc', 'd'), invoke_without_command=True)
    async def docs_group(self, ctx: commands.Context, symbol: commands.clean_content = None) -> None:
        """Lookup documentation for Python symbols."""
        await self.get_command(ctx, symbol)

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
                msg = await ctx.send(embed=doc_embed)
                await wait_for_deletion(msg, (ctx.author.id,))

    @docs_group.command(name='set', aliases=('s',))
    @commands.has_any_role(*MODERATION_ROLES)
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

        # Rebuilding the inventory can take some time, so lets send out a
        # typing event to show that the Bot is still working.
        async with ctx.typing():
            await self.refresh_inventory()
        await ctx.send(f"Added package `{package_name}` to database and refreshed inventory.")

    @docs_group.command(name='delete', aliases=('remove', 'rm', 'd'))
    @commands.has_any_role(*MODERATION_ROLES)
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
    @commands.has_any_role(*MODERATION_ROLES)
    async def refresh_command(self, ctx: commands.Context) -> None:
        """Refresh inventories and send differences to channel."""
        old_inventories = set(self.base_urls)
        with ctx.typing():
            await self.refresh_inventory()
        # Get differences of added and removed inventories
        added = ', '.join(inv for inv in self.base_urls if inv not in old_inventories)
        if added:
            added = f"+ {added}"

        removed = ', '.join(inv for inv in old_inventories if inv not in self.base_urls)
        if removed:
            removed = f"- {removed}"

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
