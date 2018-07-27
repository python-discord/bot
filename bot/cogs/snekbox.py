import datetime
import logging
import random
import re

from discord import Colour, Embed
from discord.ext.commands import (
    Bot, CommandError, Context, MissingPermissions,
    NoPrivateMessage, check, command, guild_only
)

from bot.cogs.rmq import RMQ
from bot.constants import Channels, ERROR_REPLIES, NEGATIVE_REPLIES, Roles, URLs

log = logging.getLogger(__name__)

RMQ_ARGS = {
    "durable": False,
    "arguments": {"x-message-ttl": 5000},
    "auto_delete": True
}

CODE_TEMPLATE = """
venv_file = "/snekbox/.venv/bin/activate_this.py"
exec(open(venv_file).read(), dict(__file__=venv_file))

try:
    {CODE}
except Exception as e:
    print(e)
"""

ESCAPE_REGEX = re.compile("[`\u202E\u200B]{3,}")
BYPASS_ROLES = (Roles.owner, Roles.admin, Roles.moderator, Roles.helpers)
WHITELISTED_CHANNELS = (Channels.bot,)
WHITELISTED_CHANNELS_STRING = ', '.join(f"<#{channel_id}>" for channel_id in WHITELISTED_CHANNELS)


async def channel_is_whitelisted_or_author_can_bypass(ctx: Context):
    """
    Checks that the author is either helper or above
    or the channel is a whitelisted channel.
    """

    if ctx.channel.id not in WHITELISTED_CHANNELS and ctx.author.top_role.id not in BYPASS_ROLES:
        raise MissingPermissions("You are not allowed to do that here.")

    return True


class Snekbox:
    """
    Safe evaluation using Snekbox
    """

    jobs = None  # type: dict

    def __init__(self, bot: Bot):
        self.bot = bot
        self.jobs = {}

    @property
    def rmq(self) -> RMQ:
        return self.bot.get_cog("RMQ")

    @command(name='eval', aliases=('e',))
    @guild_only()
    @check(channel_is_whitelisted_or_author_can_bypass)
    async def eval_command(self, ctx: Context, *, code: str):
        """
        Run some code. get the result back. We've done our best to make this safe, but do let us know if you
        manage to find an issue with it!
        """

        if ctx.author.id in self.jobs:
            await ctx.send(f"{ctx.author.mention} You've already got a job running - please wait for it to finish!")
            return

        log.info(f"Received code from {ctx.author.name}#{ctx.author.discriminator} for evaluation:\n{code}")
        self.jobs[ctx.author.id] = datetime.datetime.now()

        if code.startswith("```") and code.endswith("```"):
            code = code[3:-3]

        if code.startswith("python"):
            code = code[6:]
        elif code.startswith("py"):
            code = code[2:]

        code = [f"    {line.strip()}" for line in code.split("\n")]
        code = CODE_TEMPLATE.replace("{CODE}", "\n".join(code))

        try:
            await self.rmq.send_json(
                "input",
                snekid=str(ctx.author.id), message=code
            )

            async with ctx.typing():
                message = await self.rmq.consume(str(ctx.author.id), **RMQ_ARGS)
                paste_link = None

                if isinstance(message, str):
                    output = str.strip(" \n")
                else:
                    output = message.body.decode().strip(" \n")

                if "<@" in output:
                    output = output.replace("<@", "<@\u200B")  # Zero-width space

                if "<!@" in output:
                    output = output.replace("<!@", "<!@\u200B")  # Zero-width space

                if ESCAPE_REGEX.findall(output):
                    output = "Code block escape attempt detected; will not output result"
                else:
                    # the original output, to send to a pasting service if needed
                    full_output = output
                    truncated = False
                    if output.count("\n") > 0:
                        output = [f"{i:03d} | {line}" for i, line in enumerate(output.split("\n"), start=1)]
                        output = "\n".join(output)

                    if output.count("\n") > 10:
                        output = "\n".join(output.split("\n")[:10])

                        if len(output) >= 1000:
                            output = f"{output[:1000]}\n... (truncated - too long, too many lines)"
                        else:
                            output = f"{output}\n... (truncated - too many lines)"
                        truncated = True

                    elif len(output) >= 1000:
                        output = f"{output[:1000]}\n... (truncated - too long)"
                        truncated = True

                    if truncated:
                        try:
                            response = await self.bot.http_session.post(
                                URLs.paste_service.format(key="documents"),
                                data=full_output
                            )
                            data = await response.json()
                            if "key" in data:
                                paste_link = URLs.paste_service.format(key=data["key"])
                        except Exception:
                            log.exception("Failed to upload full output to paste service!")

                if output.strip():
                    if paste_link:
                        msg = f"{ctx.author.mention} Your eval job has completed.\n\n```py\n{output}\n```" \
                              f"\nFull output: {paste_link}"
                    else:
                        msg = f"{ctx.author.mention} Your eval job has completed.\n\n```py\n{output}\n```"

                    await ctx.send(msg)
                else:
                    await ctx.send(
                        f"{ctx.author.mention} Your eval job has completed.\n\n```py\n[No output]\n```"
                    )

            del self.jobs[ctx.author.id]
        except Exception:
            del self.jobs[ctx.author.id]
            raise

    @eval_command.error
    async def eval_command_error(self, ctx: Context, error: CommandError):
        embed = Embed(colour=Colour.red())

        if isinstance(error, NoPrivateMessage):
            embed.title = random.choice(NEGATIVE_REPLIES)
            embed.description = "You're not allowed to use this command in private messages."
            await ctx.send(embed=embed)

        elif isinstance(error, MissingPermissions):
            embed.title = random.choice(NEGATIVE_REPLIES)
            embed.description = f"Sorry, but you may only use this command within {WHITELISTED_CHANNELS_STRING}."
            await ctx.send(embed=embed)

        else:
            original_error = getattr(error, 'original', "no original error")
            log.error(f"Unhandled error in snekbox eval: {error} ({original_error})")
            embed.title = random.choice(ERROR_REPLIES)
            embed.description = "Some unhandled error occurred. Sorry for that!"
            await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Snekbox(bot))
    log.info("Cog loaded: Snekbox")
