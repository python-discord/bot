# coding=utf-8
from code import InteractiveInterpreter
from io import StringIO

__author__ = 'Gareth Coles'

CODE_TEMPLATE = """
async def _func():
{}
"""


class Interpreter(InteractiveInterpreter):
    write_callable = None

    def __init__(self, bot):
        _locals = {"bot": bot}
        super().__init__(_locals)

    async def run(self, code, ctx, io, *args, **kwargs):
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
