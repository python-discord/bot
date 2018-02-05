# coding=utf-8

from io import StringIO

from bot.interpreter import Interpreter

from discord.ext.commands import AutoShardedBot, Context, command, is_owner

__author__ = "Gareth Coles"


class Eval:
    """
    Bot owner only: Evaluate Python code
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot
        self.interpreter = Interpreter(bot)

    @command()
    @is_owner()
    async def eval(self, ctx: Context, *, string: str):
        """
        Bot owner only: Evaluate Python code

        Your code may be surrounded in a code fence, but it's not required.
        Scope will be preserved - variables set will be present later on.
        """

        code = string.strip()

        if code.startswith("```") and code.endswith("```"):
            if code.startswith("```python"):
                code = code[9:-3]
            elif code.startswith("```py"):
                code = code[5:-3]
            else:
                code = code[3:-3]
        elif code.startswith("`") and code.endswith("`"):
            code = code[1:-1]

        code = code.strip().strip("\n")
        io = StringIO()

        try:
            rvalue = await self.interpreter.run(code, ctx, io)
        except Exception as e:
            await ctx.send(
                f"{ctx.author.mention} **Code**\n"
                f"```py\n{code}```\n\n"
                f"**Error**\n```{e}```"
            )
        else:
            out_message = (
                f"{ctx.author.mention} **Code**\n"
                f"```py\n{code}\n```"
            )

            output = io.getvalue()

            if output:
                out_message = (
                    f"{out_message}\n\n"
                    f"**Output**\n```{output}```"
                )

            if rvalue is not None:
                out_message = (
                    f"{out_message}\n\n"
                    f"**Returned**\n```py\n{repr(rvalue)}\n```"
                )

            await ctx.send(out_message)


def setup(bot):
    bot.add_cog(Eval(bot))
    print("Cog loaded: Eval")
