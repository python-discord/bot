import functools
import logging
import re
import sys
from collections import OrderedDict
from typing import Optional, Tuple

import discord
from bs4 import BeautifulSoup
from discord.ext import commands
from markdownify import MarkdownConverter
from sphinx.ext import intersphinx

log = logging.getLogger(__name__)
logging.getLogger('urllib3').setLevel(logging.WARNING)


BASE_URLS = {
    'aiohttp': "https://aiohttp.readthedocs.io/en/stable/",
    'discord': "https://discordpy.readthedocs.io/en/rewrite/",
    'django': "https://docs.djangoproject.com/en/dev/",
    'stdlib': "https://docs.python.org/{0}.{1}/".format(*sys.version_info[:2])
}

INTERSPHINX_INVENTORIES = {
    'aiohttp': "https://aiohttp.readthedocs.io/en/stable/objects.inv",
    'discord': "https://discordpy.readthedocs.io/en/rewrite/objects.inv",
    'django': "https://docs.djangoproject.com/en/dev/_objects/",
    'stdlib': "https://docs.python.org/{0}.{1}/objects.inv".format(*sys.version_info[:2])
}

UNWANTED_SIGNATURE_SYMBOLS = ('[source]', '¶')
WHITESPACE_AFTER_NEWLINES_RE = re.compile(r"(?<=\n\n)( +)")


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

    cache = OrderedDict()

    def decorator(function):
        @functools.wraps(function)
        async def wrapper(*args):
            key = ':'.join(args[arg_offset:])

            value = cache.get(key)
            if value is None:
                if len(cache) > max_size:
                    cache.popitem(last=False)

                cache[key] = await function(*args)
            return cache[key]
        return wrapper
    return decorator


class DocMarkdownConverter(MarkdownConverter):
    def convert_code(self, el, text):
        """Undo `markdownify`s underscore escaping."""

        return f"`{text}`".replace('\\', '')

    def convert_pre(self, el, text):
        code = ''.join(el.strings)
        return f"```py\n{code}```"


def markdownify(html):
    return DocMarkdownConverter(bullets='•').convert(html)


class DummyObject(object):
    pass


class SphinxConfiguration:
    config = DummyObject()
    config.intersphinx_timeout = 3
    config.tls_verify = True


class Doc:
    def __init__(self, bot):
        self.bot = bot
        self.inventories = {}
        self.fetch_initial_inventory_data()

    def fetch_initial_inventory_data(self):
        log.debug("Loading initial intersphinx inventory data...")

        # Since Intersphinx is intended to be used with Sphinx,
        # we need to mock its configuration.
        config = SphinxConfiguration()

        for name, url in INTERSPHINX_INVENTORIES.items():
            # `fetch_inventory` performs HTTP GET and returns
            # a dictionary from the specified inventory URL.
            for _, value in intersphinx.fetch_inventory(config, '', url).items():

                # Each value has a bunch of information in the form
                # `(package_name, version, relative_url, ???)`, and we only
                # need the relative documentation URL.
                for symbol, (_, _, relative_doc_url, _) in value.items():
                    absolute_doc_url = BASE_URLS[name] + relative_doc_url
                    self.inventories[symbol] = absolute_doc_url
            log.trace(f"Fetched inventory for {name}.")

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
        if len(description) > 1000:
            description = description[:1000] + f"... [read more]({permalink})"

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

    @commands.command(name='doc()', aliases=['doc'])
    async def doc(self, ctx, symbol: commands.clean_content):
        """
        Return a documentation embed for the given symbol.

        :param ctx: Discord message context
        :param symbol: The symbol for which documentation should be returned
        """

        doc_embed = await self.get_symbol_embed(symbol)
        if doc_embed is None:
            error_embed = discord.Embed(
                description=f"Sorry, I could not find any documentation for `{symbol}`.",
                colour=discord.Colour.red()
            )
            await ctx.send(embed=error_embed)
        else:
            await ctx.send(embed=doc_embed)


def setup(bot):
    bot.add_cog(Doc(bot))
