import datetime
import logging

from aio_pika import Message
from discord import Embed, Colour
from discord.ext.commands import Bot, Context, command

from bot.cogs.rmq import RMQ
from bot.constants import Roles
from bot.decorators import with_role

log = logging.getLogger(__name__)

RMQ_ARGS = {
    "durable": False,
    "arguments": {"x-message-ttl": 5000},
    "auto_delete": True
}


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

        try:
            await self.rmq.send_json(
                "input",
                snekid=str(ctx.author.id), message=code
            )

            async def callback(message: Message):
                embed = Embed(description=f"```{message.body.decode}```", title="Code evaluation")
                embed.colour = Colour.blurple()

                await ctx.send(
                    f"{ctx.author.mention} Your eval job has completed.",
                    embed=embed
                )

                del self.jobs[ctx.author.id]

            await self.rmq.consume(str(ctx.author.id), callback, **RMQ_ARGS)
        except Exception:
            del self.jobs[ctx.author.id]
            raise


def setup(bot):
    bot.add_cog(Snekbox(bot))
    log.info("Cog loaded: Snekbox")
