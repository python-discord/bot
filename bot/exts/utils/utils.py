import difflib
import logging
import re
import unicodedata
from datetime import datetime, timedelta
from email.parser import HeaderParser
from io import StringIO
from typing import Dict, Optional, Tuple, Union

from discord import Colour, Embed, utils
from discord.ext.commands import BadArgument, Cog, Context, clean_content, command, has_any_role

from bot.bot import Bot
from bot.constants import Channels, MODERATION_ROLES, STAFF_ROLES
from bot.decorators import in_whitelist
from bot.pagination import LinePaginator
from bot.utils import messages
from bot.utils.cache import AsyncCache

log = logging.getLogger(__name__)

ZEN_OF_PYTHON = """\
Beautiful is better than ugly.
Explicit is better than implicit.
Simple is better than complex.
Complex is better than complicated.
Flat is better than nested.
Sparse is better than dense.
Readability counts.
Special cases aren't special enough to break the rules.
Although practicality beats purity.
Errors should never pass silently.
Unless explicitly silenced.
In the face of ambiguity, refuse the temptation to guess.
There should be one-- and preferably only one --obvious way to do it.
Although that way may not be obvious at first unless you're Dutch.
Now is better than never.
Although never is often better than *right* now.
If the implementation is hard to explain, it's a bad idea.
If the implementation is easy to explain, it may be a good idea.
Namespaces are one honking great idea -- let's do more of those!
"""

ICON_URL = "https://www.python.org/static/opengraph-icon-200x200.png"

# Async cache instance for PEPs
async_cache = AsyncCache()


class Utils(Cog):
    """A selection of utilities which don't have a clear category."""

    def __init__(self, bot: Bot):
        self.bot = bot

        self.base_pep_url = "http://www.python.org/dev/peps/pep-"
        self.base_github_pep_url = "https://raw.githubusercontent.com/python/peps/master/pep-"
        self.peps_listing_api_url = "https://api.github.com/repos/python/peps/contents?ref=master"

        self.peps: Dict[int, str] = {}
        self.last_refreshed_peps: Optional[datetime] = None
        self.bot.loop.create_task(self.refresh_peps_urls())

    @command()
    @in_whitelist(channels=(Channels.bot_commands,), roles=STAFF_ROLES)
    async def charinfo(self, ctx: Context, *, characters: str) -> None:
        """Shows you information on up to 50 unicode characters."""
        match = re.match(r"<(a?):(\w+):(\d+)>", characters)
        if match:
            return await messages.send_denial(
                ctx,
                "**Non-Character Detected**\n"
                "Only unicode characters can be processed, but a custom Discord emoji "
                "was found. Please remove it and try again."
            )

        if len(characters) > 50:
            return await messages.send_denial(ctx, f"Too many characters ({len(characters)}/50)")

        def get_info(char: str) -> Tuple[str, str]:
            digit = f"{ord(char):x}"
            if len(digit) <= 4:
                u_code = f"\\u{digit:>04}"
            else:
                u_code = f"\\U{digit:>08}"
            url = f"https://www.compart.com/en/unicode/U+{digit:>04}"
            name = f"[{unicodedata.name(char, '')}]({url})"
            info = f"`{u_code.ljust(10)}`: {name} - {utils.escape_markdown(char)}"
            return info, u_code

        char_list, raw_list = zip(*(get_info(c) for c in characters))
        embed = Embed().set_author(name="Character Info")

        if len(characters) > 1:
            # Maximum length possible is 502 out of 1024, so there's no need to truncate.
            embed.add_field(name='Full Raw Text', value=f"`{''.join(raw_list)}`", inline=False)

        await LinePaginator.paginate(char_list, ctx, embed, max_lines=10, max_size=2000, empty=False)

    @command()
    async def zen(self, ctx: Context, *, search_value: Union[int, str, None] = None) -> None:
        """
        Show the Zen of Python.

        Without any arguments, the full Zen will be produced.
        If an integer is provided, the line with that index will be produced.
        If a string is provided, the line which matches best will be produced.
        """
        embed = Embed(
            colour=Colour.blurple(),
            title="The Zen of Python",
            description=ZEN_OF_PYTHON
        )

        if search_value is None:
            embed.title += ", by Tim Peters"
            await ctx.send(embed=embed)
            return

        zen_lines = ZEN_OF_PYTHON.splitlines()

        # handle if it's an index int
        if isinstance(search_value, int):
            upper_bound = len(zen_lines) - 1
            lower_bound = -1 * upper_bound
            if not (lower_bound <= search_value <= upper_bound):
                raise BadArgument(f"Please provide an index between {lower_bound} and {upper_bound}.")

            embed.title += f" (line {search_value % len(zen_lines)}):"
            embed.description = zen_lines[search_value]
            await ctx.send(embed=embed)
            return

        # Try to handle first exact word due difflib.SequenceMatched may use some other similar word instead
        # exact word.
        for i, line in enumerate(zen_lines):
            for word in line.split():
                if word.lower() == search_value.lower():
                    embed.title += f" (line {i}):"
                    embed.description = line
                    await ctx.send(embed=embed)
                    return

        # handle if it's a search string and not exact word
        matcher = difflib.SequenceMatcher(None, search_value.lower())

        best_match = ""
        match_index = 0
        best_ratio = 0

        for index, line in enumerate(zen_lines):
            matcher.set_seq2(line.lower())

            # the match ratio needs to be adjusted because, naturally,
            # longer lines will have worse ratios than shorter lines when
            # fuzzy searching for keywords. this seems to work okay.
            adjusted_ratio = (len(line) - 5) ** 0.5 * matcher.ratio()

            if adjusted_ratio > best_ratio:
                best_ratio = adjusted_ratio
                best_match = line
                match_index = index

        if not best_match:
            raise BadArgument("I didn't get a match! Please try again with a different search term.")

        embed.title += f" (line {match_index}):"
        embed.description = best_match
        await ctx.send(embed=embed)

    @command(aliases=("poll",))
    @has_any_role(*MODERATION_ROLES)
    async def vote(self, ctx: Context, title: clean_content(fix_channel_mentions=True), *options: str) -> None:
        """
        Build a quick voting poll with matching reactions with the provided options.

        A maximum of 20 options can be provided, as Discord supports a max of 20
        reactions on a single message.
        """
        if len(title) > 256:
            raise BadArgument("The title cannot be longer than 256 characters.")
        if len(options) < 2:
            raise BadArgument("Please provide at least 2 options.")
        if len(options) > 20:
            raise BadArgument("I can only handle 20 options!")

        codepoint_start = 127462  # represents "regional_indicator_a" unicode value
        options = {chr(i): f"{chr(i)} - {v}" for i, v in enumerate(options, start=codepoint_start)}
        embed = Embed(title=title, description="\n".join(options.values()))
        message = await ctx.send(embed=embed)
        for reaction in options:
            await message.add_reaction(reaction)

    # region: PEP

    async def refresh_peps_urls(self) -> None:
        """Refresh PEP URLs listing in every 3 hours."""
        # Wait until HTTP client is available
        await self.bot.wait_until_ready()
        log.trace("Started refreshing PEP URLs.")

        async with self.bot.http_session.get(self.peps_listing_api_url) as resp:
            listing = await resp.json()

        log.trace("Got PEP URLs listing from GitHub API")

        for file in listing:
            name = file["name"]
            if name.startswith("pep-") and name.endswith((".rst", ".txt")):
                pep_number = name.replace("pep-", "").split(".")[0]
                self.peps[int(pep_number)] = file["download_url"]

        self.last_refreshed_peps = datetime.now()
        log.info("Successfully refreshed PEP URLs listing.")

    @command(name='pep', aliases=('get_pep', 'p'))
    async def pep_command(self, ctx: Context, pep_number: int) -> None:
        """Fetches information about a PEP and sends it to the channel."""
        # Trigger typing in chat to show users that bot is responding
        await ctx.trigger_typing()

        # Handle PEP 0 directly because it's not in .rst or .txt so it can't be accessed like other PEPs.
        if pep_number == 0:
            pep_embed = self.get_pep_zero_embed()
        else:
            if not await self.validate_pep_number(ctx, pep_number):
                return

            pep_embed = await self.get_pep_embed(ctx, pep_number)

        if pep_embed:
            await ctx.send(embed=pep_embed)
            log.trace(f"PEP {pep_number} getting and sending finished successfully. Increasing stat.")
            self.bot.stats.incr(f"pep_fetches.{pep_number}")

    @staticmethod
    def get_pep_zero_embed() -> Embed:
        """Get information embed about PEP 0."""
        pep_embed = Embed(
            title="**PEP 0 - Index of Python Enhancement Proposals (PEPs)**",
            description="[Link](https://www.python.org/dev/peps/)"
        )
        pep_embed.set_thumbnail(url=ICON_URL)
        pep_embed.add_field(name="Status", value="Active")
        pep_embed.add_field(name="Created", value="13-Jul-2000")
        pep_embed.add_field(name="Type", value="Informational")

        return pep_embed

    async def validate_pep_number(self, ctx: Context, pep_nr: int) -> bool:
        """Validate is PEP number valid. When it isn't, send error and return False. Otherwise return True."""
        if (
            pep_nr not in self.peps
            and (self.last_refreshed_peps + timedelta(minutes=30)) <= datetime.now()
            and len(str(pep_nr)) < 5
        ):
            await self.refresh_peps_urls()

        if pep_nr not in self.peps:
            log.trace(f"PEP {pep_nr} was not found")
            not_found = f"PEP {pep_nr} does not exist."
            await self.send_pep_error_embed(ctx, "PEP not found", not_found)
            return False

        return True

    def generate_pep_embed(self, pep_header: Dict, pep_nr: int) -> Embed:
        """Generate PEP embed based on PEP headers data."""
        # Assemble the embed
        pep_embed = Embed(
            title=f"**PEP {pep_nr} - {pep_header['Title']}**",
            description=f"[Link]({self.base_pep_url}{pep_nr:04})",
        )

        pep_embed.set_thumbnail(url=ICON_URL)

        # Add the interesting information
        fields_to_check = ("Status", "Python-Version", "Created", "Type")
        for field in fields_to_check:
            # Check for a PEP metadata field that is present but has an empty value
            # embed field values can't contain an empty string
            if pep_header.get(field, ""):
                pep_embed.add_field(name=field, value=pep_header[field])

        return pep_embed

    @async_cache(arg_offset=2)
    async def get_pep_embed(self, ctx: Context, pep_nr: int) -> Optional[Embed]:
        """Fetch, generate and return PEP embed. When any error occur, use `self.send_pep_error_embed`."""
        response = await self.bot.http_session.get(self.peps[pep_nr])

        if response.status == 200:
            log.trace(f"PEP {pep_nr} found")
            pep_content = await response.text()

            # Taken from https://github.com/python/peps/blob/master/pep0/pep.py#L179
            pep_header = HeaderParser().parse(StringIO(pep_content))
            return self.generate_pep_embed(pep_header, pep_nr)
        else:
            log.trace(
                f"The user requested PEP {pep_nr}, but the response had an unexpected status code: {response.status}."
            )
            error_message = "Unexpected HTTP error during PEP search. Please let us know."
            return await self.send_pep_error_embed(ctx, "Unexpected error", error_message)

    @staticmethod
    async def send_pep_error_embed(ctx: Context, title: str, description: str) -> None:
        """Send error PEP embed with `ctx.send`."""
        embed = Embed(title=title, description=description, colour=Colour.red())
        await ctx.send(embed=embed)
    # endregion


def setup(bot: Bot) -> None:
    """Load the Utils cog."""
    bot.add_cog(Utils(bot))
