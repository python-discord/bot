import difflib
import logging
import re
import unicodedata
from asyncio import TimeoutError, sleep
from email.parser import HeaderParser
from io import StringIO
from typing import Tuple, Union

from dateutil import relativedelta
from discord import Colour, Embed, Message, Role
from discord.ext.commands import BadArgument, Cog, Context, command

from bot.bot import Bot
from bot.constants import Channels, MODERATION_ROLES, Mention, STAFF_ROLES
from bot.decorators import in_channel, with_role
from bot.utils.time import humanize_delta

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


class Utils(Cog):
    """A selection of utilities which don't have a clear category."""

    def __init__(self, bot: Bot):
        self.bot = bot

        self.base_pep_url = "http://www.python.org/dev/peps/pep-"
        self.base_github_pep_url = "https://raw.githubusercontent.com/python/peps/master/pep-"

    @command(name='pep', aliases=('get_pep', 'p'))
    async def pep_command(self, ctx: Context, pep_number: str) -> None:
        """Fetches information about a PEP and sends it to the channel."""
        if pep_number.isdigit():
            pep_number = int(pep_number)
        else:
            await ctx.invoke(self.bot.get_command("help"), "pep")
            return

        # Handle PEP 0 directly because it's not in .rst or .txt so it can't be accessed like other PEPs.
        if pep_number == 0:
            return await self.send_pep_zero(ctx)

        possible_extensions = ['.txt', '.rst']
        found_pep = False
        for extension in possible_extensions:
            # Attempt to fetch the PEP
            pep_url = f"{self.base_github_pep_url}{pep_number:04}{extension}"
            log.trace(f"Requesting PEP {pep_number} with {pep_url}")
            response = await self.bot.http_session.get(pep_url)

            if response.status == 200:
                log.trace("PEP found")
                found_pep = True

                pep_content = await response.text()

                # Taken from https://github.com/python/peps/blob/master/pep0/pep.py#L179
                pep_header = HeaderParser().parse(StringIO(pep_content))

                # Assemble the embed
                pep_embed = Embed(
                    title=f"**PEP {pep_number} - {pep_header['Title']}**",
                    description=f"[Link]({self.base_pep_url}{pep_number:04})",
                )

                pep_embed.set_thumbnail(url=ICON_URL)

                # Add the interesting information
                fields_to_check = ("Status", "Python-Version", "Created", "Type")
                for field in fields_to_check:
                    # Check for a PEP metadata field that is present but has an empty value
                    # embed field values can't contain an empty string
                    if pep_header.get(field, ""):
                        pep_embed.add_field(name=field, value=pep_header[field])

            elif response.status != 404:
                # any response except 200 and 404 is expected
                found_pep = True  # actually not, but it's easier to display this way
                log.trace(f"The user requested PEP {pep_number}, but the response had an unexpected status code: "
                          f"{response.status}.\n{response.text}")

                error_message = "Unexpected HTTP error during PEP search. Please let us know."
                pep_embed = Embed(title="Unexpected error", description=error_message)
                pep_embed.colour = Colour.red()
                break

        if not found_pep:
            log.trace("PEP was not found")
            not_found = f"PEP {pep_number} does not exist."
            pep_embed = Embed(title="PEP not found", description=not_found)
            pep_embed.colour = Colour.red()

        await ctx.message.channel.send(embed=pep_embed)

    @command()
    @in_channel(Channels.bot_commands, bypass_roles=STAFF_ROLES)
    async def charinfo(self, ctx: Context, *, characters: str) -> None:
        """Shows you information on up to 25 unicode characters."""
        match = re.match(r"<(a?):(\w+):(\d+)>", characters)
        if match:
            embed = Embed(
                title="Non-Character Detected",
                description=(
                    "Only unicode characters can be processed, but a custom Discord emoji "
                    "was found. Please remove it and try again."
                )
            )
            embed.colour = Colour.red()
            await ctx.send(embed=embed)
            return

        if len(characters) > 25:
            embed = Embed(title=f"Too many characters ({len(characters)}/25)")
            embed.colour = Colour.red()
            await ctx.send(embed=embed)
            return

        def get_info(char: str) -> Tuple[str, str]:
            digit = f"{ord(char):x}"
            if len(digit) <= 4:
                u_code = f"\\u{digit:>04}"
            else:
                u_code = f"\\U{digit:>08}"
            url = f"https://www.compart.com/en/unicode/U+{digit:>04}"
            name = f"[{unicodedata.name(char, '')}]({url})"
            info = f"`{u_code.ljust(10)}`: {name} - {char}"
            return info, u_code

        charlist, rawlist = zip(*(get_info(c) for c in characters))

        embed = Embed(description="\n".join(charlist))
        embed.set_author(name="Character Info")

        if len(characters) > 1:
            embed.add_field(name='Raw', value=f"`{''.join(rawlist)}`", inline=False)

        await ctx.send(embed=embed)

    @command()
    @with_role(*MODERATION_ROLES)
    async def mention(self, ctx: Context, *, role: Role) -> None:
        """Set a role to be mentionable for a limited time."""
        if role.mentionable:
            await ctx.send(f"{role} is already mentionable!")
            return

        await role.edit(reason=f"Role unlocked by {ctx.author}", mentionable=True)

        human_time = humanize_delta(relativedelta.relativedelta(seconds=Mention.message_timeout))
        await ctx.send(
            f"{role} has been made mentionable. I will reset it in {human_time}, or when someone mentions this role."
        )

        def check(m: Message) -> bool:
            """Checks that the message contains the role mention."""
            return role in m.role_mentions

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=Mention.message_timeout)
        except TimeoutError:
            await role.edit(mentionable=False, reason="Automatic role lock - timeout.")
            await ctx.send(f"{ctx.author.mention}, you took too long. I have reset {role} to be unmentionable.")
            return

        if any(r.id in MODERATION_ROLES for r in msg.author.roles):
            await sleep(Mention.reset_delay)
            await role.edit(mentionable=False, reason=f"Automatic role lock by {msg.author}")
            await ctx.send(
                f"{ctx.author.mention}, I have reset {role} to be unmentionable as "
                f"{msg.author if msg.author != ctx.author else 'you'} sent a message mentioning it."
            )
            return

        await role.edit(mentionable=False, reason=f"Automatic role lock - unauthorised use by {msg.author}")
        await ctx.send(
            f"{ctx.author.mention}, I have reset {role} to be unmentionable "
            f"as I detected unauthorised use by {msg.author} (ID: {msg.author.id})."
        )

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
    @with_role(*MODERATION_ROLES)
    async def vote(self, ctx: Context, title: str, *options: str) -> None:
        """
        Build a quick voting poll with matching reactions with the provided options.

        A maximum of 20 options can be provided, as Discord supports a max of 20
        reactions on a single message.
        """
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

    async def send_pep_zero(self, ctx: Context) -> None:
        """Send information about PEP 0."""
        pep_embed = Embed(
            title=f"**PEP 0 - Index of Python Enhancement Proposals (PEPs)**",
            description=f"[Link](https://www.python.org/dev/peps/)"
        )
        pep_embed.set_thumbnail(url=ICON_URL)
        pep_embed.add_field(name="Status", value="Active")
        pep_embed.add_field(name="Created", value="13-Jul-2000")
        pep_embed.add_field(name="Type", value="Informational")

        await ctx.send(embed=pep_embed)


def setup(bot: Bot) -> None:
    """Load the Utils cog."""
    bot.add_cog(Utils(bot))
