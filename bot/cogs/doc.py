import logging
import sys
from typing import Optional

from discord.ext import commands
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

    async def get_doc_url(self, symbol: str) -> Optional[str]:
        return self.inventories.get(symbol)

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
            doc = await self.get_doc_url(full_symbol)
            if doc is None:
                await ctx.send(f"Sorry, I tried searching the stdlib documentation for "
                               f"`{full_symbol}`, but it didn't turn up any results.")
            else:
                await ctx.send(doc)
        else:
            doc = await self.get_doc_url(full_symbol)
            if doc is None:
                await ctx.send(f"Sorry, I could not find any documentation for `{full_symbol}`.")
            else:
                await ctx.send(doc)


def setup(bot):
    bot.add_cog(Doc(bot))
