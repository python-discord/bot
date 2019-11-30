import logging
import re
import unicodedata
from asyncio import TimeoutError, sleep
from email.parser import HeaderParser
from io import StringIO
from typing import Tuple

from dateutil import relativedelta
from discord import Colour, Embed, Message, Role
from discord.ext.commands import Bot, Cog, command

from bot.constants import Channels, MODERATION_ROLES, Mention, STAFF_ROLES
from bot.decorators import in_channel, with_role
from bot.utils.context import Context
from bot.utils.time import humanize_delta

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

        possible_extensions = ['.txt', '.rst']

        for extension in possible_extensions:
            # Attempt to fetch the PEP
            pep_url = f"{self.base_github_pep_url}{pep_number:04}{extension}"
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

                pep_embed.set_thumbnail(
                    url="https://www.python.org/static/opengraph-icon-200x200.png")

                # Add the interesting information
                if "Status" in pep_header:
                    pep_embed.add_field(name="Status", value=pep_header["Status"])
                if "Python-Version" in pep_header:
                    pep_embed.add_field(name="Python-Version", value=pep_header["Python-Version"])
                if "Created" in pep_header:
                    pep_embed.add_field(name="Created", value=pep_header["Created"])
                if "Type" in pep_header:
                    pep_embed.add_field(name="Type", value=pep_header["Type"])

                await ctx.send(embed=pep_embed)
                return

            elif response.status != 404:
                # any response except 200 and 404 is expected
                log.trace(
                    f"The user requested PEP {pep_number}, but the response had an unexpected status code: "
                    f"{response.status}.\n{response.text}")

                await ctx.send_error(error="Unexpected error",
                                     explanation="Unexpected HTTP error during PEP search. Please let us know.")
                return
        else:
            log.trace("PEP was not found")
            await ctx.send_error(error="PEP not found",
                                 explanation=f"PEP {pep_number} does not exist.")

    @command()
    @in_channel(Channels.bot, bypass_roles=STAFF_ROLES)
    async def charinfo(self, ctx: Context, *, characters: str) -> None:
        """Shows you information on up to 25 unicode characters."""
        match = re.match(r"<(a?):(\w+):(\d+)>", characters)
        if match:
            await ctx.send_error(error="Non-Character Detected",
                                 explanation="Only unicode characters can be processed, but a custom Discord emoji "
                                             "was found. Please remove it and try again.")
            return

        if len(characters) > 25:
            await ctx.send_error(error=f"Too many characters ({len(characters)}/25)")
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
            await ctx.send(
                f"{ctx.author.mention}, you took too long. I have reset {role} to be unmentionable.")
            return

        if any(r.id in MODERATION_ROLES for r in msg.author.roles):
            await sleep(Mention.reset_delay)
            await role.edit(mentionable=False, reason=f"Automatic role lock by {msg.author}")
            await ctx.send(
                f"{ctx.author.mention}, I have reset {role} to be unmentionable as "
                f"{msg.author if msg.author != ctx.author else 'you'} sent a message mentioning it."
            )
            return

        await role.edit(mentionable=False,
                        reason=f"Automatic role lock - unauthorised use by {msg.author}")
        await ctx.send(
            f"{ctx.author.mention}, I have reset {role} to be unmentionable "
            f"as I detected unauthorised use by {msg.author} (ID: {msg.author.id})."
        )


def setup(bot: Bot) -> None:
    """Utils cog load."""
    bot.add_cog(Utils(bot))
    log.info("Cog loaded: Utils")
