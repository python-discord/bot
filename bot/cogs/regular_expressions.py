import re
from typing import Iterable, Optional

from discord.ext.commands import BadArgument, Cog, Context, group

from bot.bot import Bot


def format_error(e: re.error) -> Iterable[str]:
    r"""
    Format a regexp parsing error message to display in a response.

    >>> try: re.compile("\w+(")
    ... except re.error as e: print(format_error(e))
    ['\w+(', '   ^', 'missing ), unterminated subpattern']

    Which will look like:
    | \w+(
    |    ^
    | missing ), unterminated subpattern
    """
    line_with_regexp = e.pattern
    line_with_caret = " "*e.pos + "^"
    line_with_explanation = e.msg
    return [line_with_regexp, line_with_caret, line_with_explanation]


def format_match(match: Optional[re.Match]) -> Iterable[str]:
    r"""
    Format a match result to display in a response.

    >>> format_match(re.search("(\d\d)+", "hello123456world"))
    ['    hello123456world', ' 0:      ^^^^^^', ' 1:          ^^']

    Which will look as:
    |    hello123456world
    | 0:      ^^^^^^
    | 1:          ^^
    """
    if match is None:
        return ["No match"]
    else:
        group_carets = []
        captured_positions = match.regs

        for group_index, (start, end) in enumerate(captured_positions):
            group_is_missing = (start, end) == (-1, -1)
            if not group_is_missing:
                group_carets.append(
                    f"{group_index:>2}: " + " "*start + "^"*(end - start)
                )

        return ["    " + match.string, *group_carets]


def convert_regexp(supposed_regexp: str) -> re.Pattern:
    """
    Argument converter.

    Attempts to interpret the given string as a regexp
    and returns a compiled pattern as a result.
    """
    try:
        return re.compile(supposed_regexp)
    except re.error as e:
        error_lines = "\n".join(format_error(e))
        raise BadArgument(
            "Syntax error in a regular expression: "
            f"```\n{error_lines}\n```"
        )


class RegularExpressions(Cog):
    """Commands related to regular expressions."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @group(name='regexp', aliases=('regex', 're'), invoke_without_command=True)
    async def regexp_group(self, ctx: Context) -> None:
        """Commands for exploring the misterious world of regular expressions."""
        await ctx.invoke(self.bot.get_command("help"), "regexp")

    @regexp_group.command(name='search', aliases=('s', '🔍'))
    async def match_command(self, ctx: Context, pattern: convert_regexp, test: str) -> None:
        """Look for the first match of a pattern in a string."""
        match_lines = "\n".join(format_match(pattern.search(test)))
        await ctx.send(f"```\n{match_lines}\n```")


def setup(bot: Bot) -> None:
    """Load the RegularExpressions cog."""
    bot.add_cog(RegularExpressions(bot))
