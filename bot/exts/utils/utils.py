import difflib
import re
import unicodedata

from discord import Colour, Embed, utils
from discord.ext.commands import BadArgument, Cog, Context, clean_content, command, has_any_role
from discord.utils import snowflake_time

from bot.bot import Bot
from bot.constants import Channels, MODERATION_ROLES, Roles, STAFF_PARTNERS_COMMUNITY_ROLES
from bot.converters import Snowflake
from bot.decorators import in_whitelist, not_in_blacklist
from bot.log import get_logger
from bot.pagination import LinePaginator
from bot.utils import messages, time

log = get_logger(__name__)

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
LEADS_AND_COMMUNITY = (Roles.project_leads, Roles.domain_leads, Roles.partners, Roles.python_community)


class Utils(Cog):
    """A selection of utilities which don't have a clear category."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @command()
    @not_in_blacklist(channels=(Channels.python_general,), override_roles=STAFF_PARTNERS_COMMUNITY_ROLES)
    async def charinfo(self, ctx: Context, *, characters: str) -> None:
        """Shows you information on up to 50 unicode characters."""
        match = re.match(r"<(a?):(\w+):(\d+)>", characters)
        if match:
            await messages.send_denial(
                ctx,
                "**Non-Character Detected**\n"
                "Only unicode characters can be processed, but a custom Discord emoji "
                "was found. Please remove it and try again."
            )
            return

        if len(characters) > 50:
            await messages.send_denial(ctx, f"Too many characters ({len(characters)}/50)")
            return

        def get_info(char: str) -> tuple[str, str]:
            digit = f"{ord(char):x}"
            if len(digit) <= 4:
                u_code = f"\\u{digit:>04}"
            else:
                u_code = f"\\U{digit:>08}"
            url = f"https://www.compart.com/en/unicode/U+{digit:>04}"
            name = f"[{unicodedata.name(char, 'Name not found')}]({url})"
            info = f"`{u_code.ljust(10)}`: {name} - {utils.escape_markdown(char)}"
            return info, u_code

        char_list, raw_list = zip(*(get_info(c) for c in characters), strict=True)
        embed = Embed().set_author(name="Character Info")

        if len(characters) > 1:
            # Maximum length possible is 502 out of 1024, so there's no need to truncate.
            embed.add_field(name="Full Raw Text", value=f"`{''.join(raw_list)}`", inline=False)

        await LinePaginator.paginate(char_list, ctx, embed, max_lines=10, max_size=2000, empty=False)

    @command()
    async def zen(
        self,
        ctx: Context,
        zen_rule_index: int | None,
        *,
        search_value: str | None = None
    ) -> None:
        """
        Show the Zen of Python.

        Without any arguments, the full Zen will be produced.
        If zen_rule_index is provided, the line with that index will be produced.
        If only a string is provided, the line which matches best will be produced.
        """
        embed = Embed(
            colour=Colour.og_blurple(),
            title="The Zen of Python",
            description=ZEN_OF_PYTHON
        )

        if zen_rule_index is None and search_value is None:
            embed.title += ", by Tim Peters"
            await ctx.send(embed=embed)
            return

        zen_lines = ZEN_OF_PYTHON.splitlines()

        # Prioritize passing the zen rule index
        if zen_rule_index is not None:

            upper_bound = len(zen_lines) - 1
            lower_bound = -1 * len(zen_lines)
            if not (lower_bound <= zen_rule_index <= upper_bound):
                raise BadArgument(f"Please provide an index between {lower_bound} and {upper_bound}.")

            embed.title += f" (line {zen_rule_index % len(zen_lines)}):"
            embed.description = zen_lines[zen_rule_index]
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

    @command(aliases=("snf", "snfl", "sf"))
    @in_whitelist(channels=(Channels.bot_commands,), roles=STAFF_PARTNERS_COMMUNITY_ROLES)
    async def snowflake(self, ctx: Context, *snowflakes: Snowflake) -> None:
        """Get Discord snowflake creation time."""
        if not snowflakes:
            raise BadArgument("At least one snowflake must be provided.")

        embed = Embed(colour=Colour.blue())
        embed.set_author(
            name=f"Snowflake{'s'[:len(snowflakes)^1]}",  # Deals with pluralisation
            icon_url="https://github.com/twitter/twemoji/blob/master/assets/72x72/2744.png?raw=true"
        )

        lines = []
        for snowflake in snowflakes:
            created_at = snowflake_time(snowflake)
            lines.append(f"**{snowflake}**\nCreated at {created_at} ({time.format_relative(created_at)}).")

        await LinePaginator.paginate(
            lines,
            ctx=ctx,
            embed=embed,
            max_lines=5,
            max_size=1000
        )

    @command(aliases=("poll",))
    @has_any_role(*MODERATION_ROLES, *LEADS_AND_COMMUNITY)
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


async def setup(bot: Bot) -> None:
    """Load the Utils cog."""
    await bot.add_cog(Utils(bot))
