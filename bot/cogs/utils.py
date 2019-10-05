import logging
import re
import unicodedata
from asyncio import TimeoutError, sleep, run
from contextlib import suppress
from email.parser import HeaderParser
from io import StringIO
from typing import Tuple

from discord import Colour, Embed, Message, Role
from discord.ext.commands import Bot, Cog, Context, command

from bot.constants import Channels, MODERATION_ROLES, Mention, STAFF_ROLES
from bot.decorators import in_channel, with_role

log = logging.getLogger(__name__)


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

        # Newer PEPs are written in RST instead of txt
        if pep_number > 542:
            pep_url = f"{self.base_github_pep_url}{pep_number:04}.rst"
        else:
            pep_url = f"{self.base_github_pep_url}{pep_number:04}.txt"

        # Attempt to fetch the PEP
        log.trace(f"Requesting PEP {pep_number} with {pep_url}")
        response = await self.bot.http_session.get(pep_url)

        if response.status == 200:
            log.trace("PEP found")

            pep_content = await response.text()

            # Taken from https://github.com/python/peps/blob/master/pep0/pep.py#L179
            pep_header = HeaderParser().parse(StringIO(pep_content))

            # Assemble the embed
            pep_embed = Embed(
                title=f"**PEP {pep_number} - {pep_header['Title']}**",
                description=f"[Link]({self.base_pep_url}{pep_number:04})",
            )

            pep_embed.set_thumbnail(url="https://www.python.org/static/opengraph-icon-200x200.png")

            # Add the interesting information
            if "Status" in pep_header:
                pep_embed.add_field(name="Status", value=pep_header["Status"])
            if "Python-Version" in pep_header:
                pep_embed.add_field(name="Python-Version", value=pep_header["Python-Version"])
            if "Created" in pep_header:
                pep_embed.add_field(name="Created", value=pep_header["Created"])
            if "Type" in pep_header:
                pep_embed.add_field(name="Type", value=pep_header["Type"])

        elif response.status == 404:
            log.trace("PEP was not found")
            not_found = f"PEP {pep_number} does not exist."
            pep_embed = Embed(title="PEP not found", description=not_found)
            pep_embed.colour = Colour.red()

        else:
            log.trace(f"The user requested PEP {pep_number}, but the response had an unexpected status code: "
                      f"{response.status}.\n{response.text}")

            error_message = "Unexpected HTTP error during PEP search. Please let us know."
            pep_embed = Embed(title="Unexpected error", description=error_message)
            pep_embed.colour = Colour.red()

        await ctx.message.channel.send(embed=pep_embed)

    @command()
    @in_channel(Channels.bot, bypass_roles=STAFF_ROLES)
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

    @staticmethod
    def readable_time(seconds: int) -> str:
        minutes, seconds = divmod(seconds, 60)

        if minutes:
            fmt = '{m}min {s}sec'
        else:
            fmt = '{s}sec'

        return fmt.format(m=minutes, s=seconds)

    @command()
    @with_role(*MODERATION_ROLES)
    async def mention(self, ctx: Context, *, role: Role) -> None:
        """Set a role to be mentionable for a limited time."""
        if role.mentionable:
            await ctx.send(f"{role} is already mentionable!")
            return

        await role.edit(reason=f"Role unlocked by {ctx.author}", mentionable=True)

        await ctx.send(
            f"{role} has been made mentionable. I will reset it in "
            f"{self.readable_time(Mention.message_timeout)} seconds, or when a staff member mentions this role."
        )

        def check(m: Message) -> bool:
            """Checks that the message contains the role mention and the user is a staff member."""
            if not any(m.id in MODERATION_ROLES for m in m.author.roles) and role in m.role_mentions:
                run(ctx.send(
                    f"{ctx.author.mention}, {m.author} has mentioned the role you set to mentionable."
                )
                )
                return False

            return role in m.role_mentions

        with suppress(TimeoutError):
            await self.bot.wait_for("message", check=check, timeout=Mention.message_timeout)
            await sleep(Mention.reset_delay)

        await role.edit(mentionable=False)
        await ctx.send(f"{ctx.author.mention}, I have reset {role} to be unmentionable.")


def setup(bot: Bot) -> None:
    """Utils cog load."""
    bot.add_cog(Utils(bot))
    log.info("Cog loaded: Utils")
