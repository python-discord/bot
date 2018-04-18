import logging
import sys
import re
from typing import Optional

import aiohttp
import discord
from bs4 import BeautifulSoup
from discord.ext import commands
from markdownify import MarkdownConverter
from sphinx.ext import intersphinx

log = logging.getLogger(__name__)


BASE_URLS = {
    'aiohttp': "https://aiohttp.readthedocs.io/en/stable/",
    'discord': "https://discordpy.readthedocs.io/en/rewrite/",
    'django': "https://docs.djangoproject.com/en/dev/",
    'stdlib': "https://docs.python.org/%d.%d/" % sys.version_info[:2]
}

INTERSPHINX_INVENTORIES = {
    'aiohttp': "https://aiohttp.readthedocs.io/en/stable/objects.inv",
    'discord': "https://discordpy.readthedocs.io/en/rewrite/objects.inv",
    'django': "https://docs.djangoproject.com/en/dev/_objects/",
    'stdlib': "https://docs.python.org/%d.%d/objects.inv" % sys.version_info[:2]
}

WHITESPACE_AFTER_NEWLINES_RE = re.compile(r"(?<=\n\n)( +)")


class DocMarkdownConverter(MarkdownConverter):
    def convert_code(self, el, text):
        # Some part of `markdownify` believes that it should escape
        # underscored in variable names. I do not.
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
        config = SphinxConfiguration()
        for name, url in INTERSPHINX_INVENTORIES.items():
            for _, value in intersphinx.fetch_inventory(config, '', url).items():
                for symbol, info_tuple in value.items():
                    relative_doc_url = info_tuple[2]
                    absolute_doc_url = BASE_URLS[name] + relative_doc_url
                    self.inventories[symbol] = absolute_doc_url
            log.trace(f"Fetched inventory for {name}.")

    async def get_symbol_html(self, symbol: str) -> Optional[str]:
        url = self.inventories.get(symbol)
        if url is None:
            return None

        async with aiohttp.ClientSession() as cs:
            async with cs.get(url) as response:
                html = await response.text(encoding='utf-8')

        symbol_id = url.split('#')[-1]
        soup = BeautifulSoup(html, 'html.parser')
        symbol_heading = soup.find(id=symbol_id)
        signature_buffer = []

        for tag in symbol_heading.strings:
            if tag not in ('¶', '[source]'):
                signature_buffer.append(tag.replace('\\', ''))

        signature = ''.join(signature_buffer)
        description = str(symbol_heading.next_sibling.next_sibling).replace('¶', '')

        return signature, description

    async def get_symbol_embed(self, symbol: str) -> Optional[discord.Embed]:
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

    @commands.command()
    async def doc(self, ctx, *, full_symbol: commands.clean_content):
        """
        Return documentation for the given symbol.
        """

        if '.' in full_symbol:
            package, dotted_path = full_symbol.split('.', maxsplit=1)
        else:
            package = full_symbol
            dotted_path = ''

        if not dotted_path or package not in self.inventories:
            doc_embed = await self.get_symbol_embed(full_symbol)
            if doc_embed is None:
                await ctx.send(f"Sorry, I tried searching the stdlib documentation for "
                               f"`{full_symbol}`, but it didn't turn up any results.")
            else:
                await ctx.send(embed=doc_embed)
        else:
            doc_embed = await self.get_symbol_embed(full_symbol)
            if doc_embed is None:
                await ctx.send(f"Sorry, I could not find any documentation for `{full_symbol}`.")
            else:
                await ctx.send(embed=doc_embed)


def setup(bot):
    bot.add_cog(Doc(bot))
