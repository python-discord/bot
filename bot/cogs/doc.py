import asyncio
import functools
import logging
import random
import re
from collections import OrderedDict
from ssl import CertificateError
from typing import Dict, List, Optional, Tuple

import discord
from aiohttp import ClientConnectorError
from bs4 import BeautifulSoup
from discord.ext import commands
from markdownify import MarkdownConverter
from requests import ConnectionError
from sphinx.ext import intersphinx

from bot.constants import ERROR_REPLIES, Keys, Roles, URLs
from bot.decorators import with_role


log = logging.getLogger(__name__)
logging.getLogger('urllib3').setLevel(logging.WARNING)


UNWANTED_SIGNATURE_SYMBOLS = ('[source]', '¶')
WHITESPACE_AFTER_NEWLINES_RE = re.compile(r"(?<=\n\n)(\s+)")


def async_cache(max_size=128, arg_offset=0):
    """
    LRU cache implementation for coroutines.

    :param max_size:
    Specifies the maximum size the cache should have.
    Once it exceeds the maximum size, keys are deleted in FIFO order.
    :param arg_offset:
    The offset that should be applied to the coroutine's arguments
    when creating the cache key. Defaults to `0`.
    """

    # Assign the cache to the function itself so we can clear it from outside.
    async_cache.cache = OrderedDict()

    def decorator(function):
        @functools.wraps(function)
        async def wrapper(*args):
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
    def convert_code(self, el, text):
        """Undo `markdownify`s underscore escaping."""

        return f"`{text}`".replace('\\', '')

    def convert_pre(self, el, text):
        """Wrap any codeblocks in `py` for syntax highlighting."""

        code = ''.join(el.strings)
        return f"```py\n{code}```"


def markdownify(html):
    return DocMarkdownConverter(bullets='•').convert(html)


class DummyObject(object):
    """
    A dummy object which supports assigning anything,
    which the builtin `object()` does not support normally.
    """


class SphinxConfiguration:
    """Dummy configuration for use with intersphinx."""

    config = DummyObject()
    config.intersphinx_timeout = 3
    config.tls_verify = True


class ValidPythonIdentifier(commands.Converter):
    """
    A converter that checks whether the given string is a valid Python identifier.

    This is used to have package names
    that correspond to how you would use
    the package in your code, e.g.
    `import package`. Raises `BadArgument`
    if the argument is not a valid Python
    identifier, and simply passes through
    the given argument otherwise.
    """

    @staticmethod
    async def convert(ctx, argument: str):
        if not argument.isidentifier():
            raise commands.BadArgument(f"`{argument}` is not a valid Python identifier")
        return argument


class DocumentationBaseURL(commands.Converter):
    """
    Represents a documentation base URL.

    This converter checks whether the given
    URL can be reached and requesting it returns
    a status code of 200. If not, `BadArgument`
    is raised. Otherwise, it simply passes through the given URL.
    """

    @staticmethod
    async def convert(ctx, url: str):
        try:
            async with ctx.bot.http_session.get(url) as resp:
                if resp.status != 200:
                    raise commands.BadArgument(
                        f"HTTP GET on `{url}` returned status `{resp.status_code}`, expected 200"
                    )
        except CertificateError:
            if url.startswith('https'):
                raise commands.BadArgument(
                    f"Got a `CertificateError` for URL `{url}`. Does it support HTTPS?"
                )
            raise commands.BadArgument(f"Got a `CertificateError` for URL `{url}`.")
        except ValueError:
            raise commands.BadArgument(f"`{url}` doesn't look like a valid hostname to me.")
        except ClientConnectorError:
            raise commands.BadArgument(f"Cannot connect to host with URL `{url}`.")
        return url


class InventoryURL(commands.Converter):
    """
    Represents an Intersphinx inventory URL.

    This converter checks whether intersphinx
    accepts the given inventory URL, and raises
    `BadArgument` if that is not the case.
    Otherwise, it simply passes through the given URL.
    """

    @staticmethod
    async def convert(ctx, url: str):
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


class Doc:
    def __init__(self, bot):
        self.base_urls = {}
        self.bot = bot
        self.inventories = {}
        self.headers = {"X-API-KEY": Keys.site_api}

    async def on_ready(self):
        await self.refresh_inventory()

    async def update_single(
        self, package_name: str, base_url: str, inventory_url: str, config: SphinxConfiguration
    ):
        """
        Rebuild the inventory for a single package.

        :param package_name: The package name to use, appears in the log.
        :param base_url: The root documentation URL for the specified package.
                         Used to build absolute paths that link to specific symbols.
        :param inventory_url: The absolute URL to the intersphinx inventory.
                              Fetched by running `intersphinx.fetch_inventory` in an
                              executor on the bot's event loop.
        :param config: A `SphinxConfiguration` instance to mock the regular sphinx
                       project layout. Required for use with intersphinx.
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

    async def refresh_inventory(self):
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
            ) for package in await self.get_all_packages()
        ]
        await asyncio.gather(*coros)

    async def get_symbol_html(self, symbol: str) -> Optional[Tuple[str, str]]:
        """
        Given a Python symbol, return its signature and description.

        :param symbol: The symbol for which HTML data should be returned.
        :return:
        A tuple in the form (str, str), or `None`.
        The first tuple element is the signature of the given
        symbol as a markup-free string, and the second tuple
        element is the description of the given symbol with HTML
        markup included. If the given symbol could not be found,
        returns `None`.
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
        Using `get_symbol_html`, attempt to scrape and
        fetch the data for the given `symbol`, and build
        a formatted embed out of its contents.

        :param symbol: The symbol for which the embed should be returned
        :return:
        If the symbol is known, an Embed with documentation about it.
        Otherwise, `None`.
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

        return discord.Embed(
            title=f'`{symbol}`',
            url=permalink,
            description=f"```py\n{signature}```{description}"
        )

    async def get_all_packages(self) -> List[Dict[str, str]]:
        """
        Performs HTTP GET to get all packages from the website.

        :return:
        A list of packages, in the following format:
        [
            {
                "package": "example-package",
                "base_url": "https://example.readthedocs.io",
                "inventory_url": "https://example.readthedocs.io/objects.inv"
            },
            ...
        ]
        `package` specifies the package name, for example 'aiohttp'.
        `base_url` specifies the documentation root URL, used to build absolute links.
        `inventory_url` specifies the location of the Intersphinx inventory.
        """

        async with self.bot.http_session.get(URLs.site_docs_api, headers=self.headers) as resp:
            return await resp.json()

    async def get_package(self, package_name: str) -> Optional[Dict[str, str]]:
        """
        Performs HTTP GET to get the specified package from the documentation database.

        :param package_name: The package name for which information should be returned.
        :return:
        Either a dictionary with information in the following format:
        {
            "package": "example-package",
            "base_url": "https://example.readthedocs.io",
            "inventory_url": "https://example.readthedocs.io/objects.inv"
        }
        or `None` if the site didn't returned no results for the given name.
        """

        params = {"package": package_name}

        async with self.bot.http_session.get(URLs.site_docs_api,
                                             headers=self.headers,
                                             params=params) as resp:
            package_data = await resp.json()
            if not package_data:
                return None
            return package_data[0]

    async def set_package(self, name: str, base_url: str, inventory_url: str) -> Dict[str, bool]:
        """
        Performs HTTP POST to add a new package to the website's documentation database.

        :param name: The name of the package, for example `aiohttp`.
        :param base_url: The documentation root URL, used to build absolute links.
        :param inventory_url: The absolute URl to the intersphinx inventory of the package.

        :return: The JSON response of the server, which is always:
        {
            "success": True
        }
        """

        package_json = {
            'package': name,
            'base_url': base_url,
            'inventory_url': inventory_url
        }

        async with self.bot.http_session.post(URLs.site_docs_api,
                                              headers=self.headers,
                                              json=package_json) as resp:
            return await resp.json()

    async def delete_package(self, name: str) -> bool:
        """
        Performs HTTP DELETE to delete the specified package from the documentation database.

        :param name: The package to delete.

        :return: `True` if successful, `False` if the package is unknown.
        """

        package_json = {'package': name}

        async with self.bot.http_session.delete(URLs.site_docs_api,
                                                headers=self.headers,
                                                json=package_json) as resp:
            changes = await resp.json()
            return changes["deleted"] == 1  # Did the package delete successfully?

    @commands.command(name='docs.get()', aliases=['docs.get'])
    async def get_command(self, ctx, symbol: commands.clean_content = None):
        """
        Return a documentation embed for a given symbol.
        If no symbol is given, return a list of all available inventories.

        :param ctx: Discord message context
        :param symbol: The symbol for which documentation should be returned,
                       or nothing to get a list of all inventories

        Examples:
            bot.docs.get('aiohttp')
            bot.docs['aiohttp']
        """

        if symbol is None:
            all_inventories = "\n".join(
                f"• [`{name}`]({url})" for name, url in self.base_urls.items()
            )
            inventory_embed = discord.Embed(
                title="All inventories",
                description=all_inventories or "*Seems like there's nothing here yet.*",
                colour=discord.Colour.blue()
            )
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

    @with_role(Roles.admin, Roles.owner, Roles.moderator)
    @commands.command(name='docs.set()', aliases=['docs.set'])
    async def set_command(
        self, ctx, package_name: ValidPythonIdentifier,
        base_url: DocumentationBaseURL, inventory_url: InventoryURL
    ):
        """
        Adds a new documentation metadata object to the site's database.
        The database will update the object, should an existing item
        with the specified `package_name` already exist.

        :param ctx: Discord message context
        :param package_name: The package name, for example `aiohttp`.
        :param base_url: The package documentation's root URL, used to build absolute links.
        :param inventory_url: The intersphinx inventory URL.

        Example:
            bot.docs.set(
                'discord',
                'https://discordpy.readthedocs.io/en/rewrite/',
                'https://discordpy.readthedocs.io/en/rewrite/objects.inv'
            )
        """

        await self.set_package(package_name, base_url, inventory_url)
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

    @with_role(Roles.admin, Roles.owner, Roles.moderator)
    @commands.command(name='docs.delete()', aliases=['docs.delete', 'docs.remove()', 'docs.remove'])
    async def delete_command(self, ctx, package_name: ValidPythonIdentifier):
        """
        Removes the specified package from the database.

        :param ctx: Discord message context
        :param package_name: The package name, for example `aiohttp`.

        Examples:
            bot.tags.delete('aiohttp')
            bot.tags['aiohttp'] = None
        """

        success = await self.delete_package(package_name)
        if success:

            async with ctx.typing():
                # Rebuild the inventory to ensure that everything
                # that was from this package is properly deleted.
                await self.refresh_inventory()
            await ctx.send(f"Successfully deleted `{package_name}` and refreshed inventory.")

        else:
            await ctx.send(
                f"Can't find any package named `{package_name}` in the database. "
                "View all known packages by using `docs.get()`."
            )

    @get_command.error
    @delete_command.error
    @set_command.error
    async def general_command_error(self, ctx, error: commands.CommandError):
        """
        Handle the `BadArgument` error caused by
        the commands when argument validation fails.

        :param ctx: Discord message context of the message creating the error
        :param error: The error raised, usually `BadArgument`
        """

        if isinstance(error, commands.BadArgument):
            embed = discord.Embed(
                title=random.choice(ERROR_REPLIES),
                description=f"Error: {error}",
                colour=discord.Colour.red()
            )
            await ctx.send(embed=embed)
        else:
            log.exception(f"Unhandled error: {error}")


def setup(bot):
    bot.add_cog(Doc(bot))
