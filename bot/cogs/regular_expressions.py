import re
from typing import Iterable, Optional, Union

import regex
from discord.ext.commands import BadArgument, Cog, Context, Converter, group

from bot.bot import Bot


REGEX_TIMEOUT = 0.05  # maximum time until


def format_error(e: Union[re.error, regex.error]) -> Iterable[str]:
    r"""
    Format a regexp parsing error message to display in a response.

    >>> try: re.compile("\w+(")
    ... except re.error as e: print(format_error(e))
    ['- \w+(', '-    ^', '- missing ), unterminated subpattern']

    Which will look like:
    | \w+(
    |    ^
    | missing ), unterminated subpattern
    (everything colored red)
    """
    line_with_regexp = "- " + e.pattern
    line_with_caret = "- " + " "*e.pos + "^"
    line_with_explanation = "- " + e.msg
    return [line_with_regexp, line_with_caret, line_with_explanation]


def format_match(match: Optional[re.Match]) -> Iterable[str]:
    r"""
    Format a match result to display in a response.

    >>> format_match(re.search("(\d\d)+", "hello123456world"))
    ['    hello123456world', '+  0:      123456', '+  1:          56']

    Which will look as:
    |    hello123456world
    | 0:      123456
    | 1:          56
    (the last two lines will be green)
    """
    if match is None:
        return ["No match"]
    else:
        group_carets = []
        captured_positions = match.regs

        for group_index, (start, end) in enumerate(captured_positions):
            group_is_missing = (start, end) == (-1, -1)
            if not group_is_missing:
                # TODO: display zero-width groups (how?)
                group_carets.append(
                    f"+ {group_index:>2}: " + " "*start + match.string[start:end]
                )

        return ["      " + match.string, *group_carets]


def match_and_format(pattern: regex.Regex, test: str) -> str:
    """Attempt to match a regex with a test string and return a formatted result."""
    try:
        match_lines = "\n".join(format_match(pattern.search(test, timeout=REGEX_TIMEOUT)))
        return f"\n```diff\n{match_lines}\n```"
    except TimeoutError:
        return ":x: Searching with this regular expression took too much time"


class ConvertRegex(Converter):
    """
    Argument converter.

    Attempts to interpret the given string as a regex
    and returns a compiled pattern as a result.
    """

    def __init__(self, supports_extended_features: bool = False):
        self.supports_extended_features = supports_extended_features

    async def convert(self, ctx: Context, supposed_regex: str) -> regex.Regex:
        """
        Attempt to parse the input string as a regular expression.

        If `self.supports_extended_features` is False, then the regex is forced
        to be compatible with `re`.
        """
        try:
            if not self.supports_extended_features:
                re.compile(supposed_regex)
            return regex.compile(supposed_regex)
        except (regex.error, re.error) as e:
            error_lines = "\n".join(format_error(e))
            raise BadArgument(
                ":x: Syntax error in a regular expression: \n"
                f"```diff\n{error_lines}\n```"
            )


Regex = ConvertRegex(supports_extended_features=False)
ExtendedRegex = ConvertRegex(supports_extended_features=True)


class RegularExpressions(Cog):
    """Commands related to regular expressions."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @group(name='regexp', aliases=('regex', 're'), invoke_without_command=True)
    async def regexp_group(self, ctx: Context) -> None:
        """Commands for exploring the mysterious world of regular expressions."""
        await ctx.invoke(self.bot.get_command("help"), "regexp")

    @regexp_group.command(name='search', aliases=('find', 's'))
    async def match_command(self, ctx: Context, pattern: Regex, test: str) -> None:
        """Look for the first match of a pattern in a string."""
        await ctx.send(match_and_format(pattern, test))

    @regexp_group.command(name='search+', aliases=('find+', 's+'))
    async def match_plus_command(self, ctx: Context, pattern: ExtendedRegex, test: str) -> None:
        """
        Look for the first match of a pattern in a string.

        Enables additional features from the
        https://pypi.org/project/regex module.
        """
        await ctx.send(match_and_format(pattern, test))


def setup(bot: Bot) -> None:
    """Load the RegularExpressions cog."""
    bot.add_cog(RegularExpressions(bot))
