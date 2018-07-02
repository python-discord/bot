import datetime
import logging

from discord.ext.commands import Bot, Context, command

from bot.cogs.rmq import RMQ

log = logging.getLogger(__name__)

RMQ_ARGS = {
    "durable": False,
    "arguments": {"x-message-ttl": 5000},
    "auto_delete": True
}

CODE_TEMPLATE = """
try:
    {CODE}
except Exception as e:
    print(e)
"""


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

    @command(name="snekbox.eval()", aliases=["snekbox.eval", "eval()", "eval"])
    async def do_eval(self, ctx: Context, code: str):
        """
        Run some code. get the result back. We've done our best to make this safe, but do let us know if you
        manage to find an issue with it!

        Remember, your code must be within some kind of string. Why not surround your code with quotes or put it in
        a docstring?
        """

        if ctx.author.id in self.jobs:
            await ctx.send(f"{ctx.author.mention} You've already got a job running - please wait for it to finish!")
            return

        log.info(f"Received code from {ctx.author.name}#{ctx.author.discriminator} for evaluation:\n{code}")
        self.jobs[ctx.author.id] = datetime.datetime.now()

        code = [f"    {line}" for line in code.split("\n")]
        code = CODE_TEMPLATE.replace("{CODE}", "\n".join(code))

        try:
            await self.rmq.send_json(
                "input",
                snekid=str(ctx.author.id), message=code
            )

            async with ctx.typing():
                message = await self.rmq.consume(str(ctx.author.id), **RMQ_ARGS)

                if isinstance(message, str):
                    output = str.strip(" \n")
                else:
                    output = message.body.decode().strip(" \n")

                if "```" in output:
                    output = "Code block escape attempt detected; will not output result"
                else:
                    if output.count("\n") > 0:
                        output = [f"{i:03d} | {line}" for i, line in enumerate(output.split("\n"), start=1)]
                        output = "\n".join(output)

                    if output.count("\n") > 10:
                        output = "\n".join(output.split("\n")[:10])

                        if len(output) >= 1000:
                            output = f"{output[:1000]}\n... (truncated - too long, too many lines)"
                        else:
                            output = f"{output}\n... (truncated - too many lines)"

                    elif len(output) >= 1000:
                        output = f"{output[:1000]}\n... (truncated - too long)"

                await ctx.send(
                    f"{ctx.author.mention} Your eval job has completed.\n\n```py\n{output}\n```"
                )

            del self.jobs[ctx.author.id]
        except Exception:
            del self.jobs[ctx.author.id]
            raise


def setup(bot):
    bot.add_cog(Snekbox(bot))
    log.info("Cog loaded: Snekbox")
