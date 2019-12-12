from code import InteractiveInterpreter
from io import StringIO
from typing import Any

from discord.ext.commands import Context

from bot.bot import Bot

CODE_TEMPLATE = """
async def _func():
{0}
"""


class Interpreter(InteractiveInterpreter):
    """
    Subclass InteractiveInterpreter to specify custom run functionality.

    Helper class for internal eval.
    """

    write_callable = None

    def __init__(self, bot: Bot):
        locals_ = {"bot": bot}
        super().__init__(locals_)

    async def run(self, code: str, ctx: Context, io: StringIO, *args, **kwargs) -> Any:
        """Execute the provided source code as the bot & return the output."""
        self.locals["_rvalue"] = []
        self.locals["ctx"] = ctx
        self.locals["print"] = lambda x: io.write(f"{x}\n")

        code_io = StringIO()

        for line in code.split("\n"):
            code_io.write(f"    {line}\n")

        code = CODE_TEMPLATE.format(code_io.getvalue())
        del code_io

        self.runsource(code, *args, **kwargs)
        self.runsource("_rvalue = _func()", *args, **kwargs)

        rvalue = await self.locals["_rvalue"]

        del self.locals["_rvalue"]
        del self.locals["ctx"]
        del self.locals["print"]

        return rvalue
