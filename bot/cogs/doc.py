import asyncio
import functools
import logging
import re
import textwrap
from collections import OrderedDict
from typing import Any, Callable, Optional, Tuple

import discord
from bs4 import BeautifulSoup
from bs4.element import PageElement
from discord.ext import commands
from markdownify import MarkdownConverter
from requests import ConnectionError
from sphinx.ext import intersphinx

from bot.constants import MODERATION_ROLES
from bot.converters import ValidPythonIdentifier, ValidURL
from bot.decorators import with_role
from bot.pagination import LinePaginator


log = logging.getLogger(__name__)
logging.getLogger('urllib3').setLevel(logging.WARNING)


UNWANTED_SIGNATURE_SYMBOLS = ('[source]', '¶')
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

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Refresh documentation inventory."""
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

        fetch_func = functools.partial(intersphinx.fetch_inventory, config, '', inventory_url)
        for _, value in (await self.bot.loop.run_in_executor(None, fetch_func)).items():
            # Each value has a bunch of information in the form
            # `(package_name, version, relative_url, ???)`, and we only
            # need the relative documentation URL.
            for symbol, (_, _, relative_doc_url, _) in value.items():
                absolute_doc_url = base_url + relative_doc_url
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

    async def get_symbol_html(self, symbol: str) -> Optional[Tuple[str, str]]:
        """
        Given a Python symbol, return its signature and description.

        Returns a tuple in the form (str, str), or `None`.

        The first tuple element is the signature of the given symbol as a markup-free string, and
        the second tuple element is the description of the given symbol with HTML markup included.

        If the given symbol could not be found, returns `None`.
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
        signature_buffer = []

        # Traverse the tags of the signature header and ignore any
        # unwanted symbols from it. Add all of it to a temporary buffer.
        for tag in symbol_heading.strings:
            if tag not in UNWANTED_SIGNATURE_SYMBOLS:
                signature_buffer.append(tag.replace('\\', ''))

        signature = ''.join(signature_buffer)
        description = str(symbol_heading.next_sibling.next_sibling).replace('¶', '')

        return signature, description

    @async_cache(arg_offset=1)
    async def get_symbol_embed(self, symbol: str) -> Optional[discord.Embed]:
        """
        Attempt to scrape and fetch the data for the given `symbol`, and build an embed from its contents.

        If the symbol is known, an Embed with documentation about it is returned.
        """
        scraped_html = await self.get_symbol_html(symbol)
        if scraped_html is None:
            return None

        signature = scraped_html[0]
        permalink = self.inventories[symbol]
        description = markdownify(scraped_html[1])

        # Truncate the description of the embed to the last occurrence
        # of a double newline (interpreted as a paragraph) before index 1000.
        if len(description) > 1000:
            shortened = description[:1000]
            last_paragraph_end = shortened.rfind('\n\n')
            description = description[:last_paragraph_end] + f"... [read more]({permalink})"

        description = WHITESPACE_AFTER_NEWLINES_RE.sub('', description)

        if not signature:
            # It's some "meta-page", for example:
            # https://docs.djangoproject.com/en/dev/ref/views/#module-django.views
            return discord.Embed(
                title=f'`{symbol}`',
                url=permalink,
                description="This appears to be a generic page not tied to a specific symbol."
            )

        signature = textwrap.shorten(signature, 500)
        return discord.Embed(
            title=f'`{symbol}`',
            url=permalink,
            description=f"```py\n{signature}```{description}"
        )

    @commands.group(name='docs', aliases=('doc', 'd'), invoke_without_command=True)
    async def docs_group(self, ctx: commands.Context, symbol: commands.clean_content = None) -> None:
        """Lookup documentation for Python symbols."""
        await ctx.invoke(self.get_command)

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
                await ctx.send(embed=error_embed)
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
                    discord \
                    https://discordpy.readthedocs.io/en/rewrite/ \
                    https://discordpy.readthedocs.io/en/rewrite/objects.inv
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


def setup(bot: commands.Bot) -> None:
    """Doc cog load."""
    bot.add_cog(Doc(bot))
    log.info("Cog loaded: Doc")
