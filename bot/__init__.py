# coding=utf-8
import ast
import logging
import sys
from logging import Logger, StreamHandler
from logging.handlers import SysLogHandler

import discord.ext.commands.view
from logmatic import JsonFormatter

from bot.constants import PAPERTRAIL_ADDRESS, PAPERTRAIL_PORT

logging.TRACE = 5
logging.addLevelName(logging.TRACE, "TRACE")


def monkeypatch_trace(self, msg, *args, **kwargs):
    """
    Log 'msg % args' with severity 'TRACE'.

    To pass exception information, use the keyword argument exc_info with
    a true value, e.g.

    logger.trace("Houston, we have an %s", "interesting problem", exc_info=1)
    """
    if self.isEnabledFor(logging.TRACE):
        self._log(logging.TRACE, msg, args, **kwargs)


Logger.trace = monkeypatch_trace

# Set up logging
logging_handlers = []

if PAPERTRAIL_ADDRESS:
    papertrail_handler = SysLogHandler(address=(PAPERTRAIL_ADDRESS, PAPERTRAIL_PORT))
    papertrail_handler.setLevel(logging.DEBUG)
    logging_handlers.append(papertrail_handler)

logging_handlers.append(StreamHandler(stream=sys.stderr))

json_handler = logging.FileHandler(filename="log.json", mode="w")
json_handler.formatter = JsonFormatter()
logging_handlers.append(json_handler)

logging.basicConfig(
    format="%(asctime)s pd.beardfist.com Bot: | %(name)30s | %(levelname)8s | %(message)s",
    datefmt="%b %d %H:%M:%S",
    level=logging.TRACE,
    handlers=logging_handlers
)

log = logging.getLogger(__name__)

# Silence discord and websockets
logging.getLogger("discord.client").setLevel(logging.ERROR)
logging.getLogger("discord.gateway").setLevel(logging.ERROR)
logging.getLogger("discord.state").setLevel(logging.ERROR)
logging.getLogger("discord.http").setLevel(logging.ERROR)
logging.getLogger("websockets.protocol").setLevel(logging.ERROR)


def _skip_string(self, string: str) -> bool:
    """
    Our version of the skip_string method from
    discord.ext.commands.view; used to find
    the prefix in a message, but allowing prefix
    to ignore case sensitivity
    """

    strlen = len(string)
    if self.buffer.lower()[self.index:self.index + strlen] == string:
        self.previous = self.index
        self.index += strlen
        return True
    return False


def _get_word(self) -> str:
    """
    Invokes the get_word method from
    discord.ext.commands.view used to find
    the bot command part of a message, but
    allows the command to ignore case sensitivity,
    and allows commands to have Python syntax.

    Example of valid Python syntax calls:
    ------------------------------
    bot.tags.set("test", 'a dark, dark night')
    bot.help(tags.delete)
    bot.hELP(tags.delete)
    """

    pos = 0
    while not self.eof:
        try:
            current = self.buffer[self.index + pos]
            if current.isspace() or current == "(" or current == "[":
                break
            pos += 1
        except IndexError:
            break

    self.previous = self.index
    result = self.buffer[self.index:self.index + pos]
    self.index += pos
    next = None

    # Check what's after the '('
    if len(self.buffer) != self.index:
        next = self.buffer[self.index + 1]

    # Is it possible to parse this without syntax error?
    syntax_valid = True
    try:
        ast.literal_eval(self.buffer[self.index:])
    except SyntaxError:
        log.warning("The command cannot be parsed by ast.literal_eval because it raises a SyntaxError.")
        # TODO: It would be nice if this actually made the bot return a SyntaxError. ClickUp #1b12z  # noqa: T000
        syntax_valid = False

    # Conditions for a valid, parsable command.
    python_parse_conditions = (
        current == "("
        and next
        and next != ")"
        and syntax_valid
    )

    if python_parse_conditions:
        log.debug(f"A python-style command was used. Attempting to parse. Buffer is {self.buffer}. "
                  "A step-by-step can be found in the trace log.")

        # Parse the args
        log.trace("Parsing command with ast.literal_eval.")
        args = self.buffer[self.index:]
        args = ast.literal_eval(args)

        # Force args into container
        if not isinstance(args, tuple):
            args = (args,)

        # Type validate and format
        new_args = []
        for arg in args:

            # Other types get converted to strings
            if not isinstance(arg, str):
                log.trace(f"{arg} is not a str, casting to str.")
                arg = str(arg)

            # Allow using double quotes within triple double quotes
            arg = arg.replace('"', '\\"')

            # Adding double quotes to every argument
            log.trace(f"Wrapping all args in double quotes.")
            new_args.append(f'"{arg}"')

        # Add the result to the buffer
        new_args = " ".join(new_args)
        self.buffer = f"{self.buffer[:self.index]} {new_args}"
        log.trace(f"Modified the buffer. New buffer is now {self.buffer}")

        # Recalibrate the end since we've removed commas
        self.end = len(self.buffer)

    elif current == "(" and next == ")":
        # Move the cursor to capture the ()'s
        log.debug("User called command without providing arguments.")
        pos += 2
        result = self.buffer[self.previous:self.index + (pos+2)]
        self.index += 2

    # Check if a command in the form of `bot.tags['ask']`
    # or alternatively `bot.tags['ask'] = 'whatever'` was used.
    elif current == "[":
        def clean_argument(arg: str) -> str:
            """Helper function to remove any characters we don't care about."""

            return arg.strip("[]'\" ").replace('"', '\\"')

        log.trace(f"Got a command candidate for getitem / setitem mimick: {self.buffer}")
        # Syntax is `bot.tags['ask']` => mimic `getattr`
        if self.buffer.endswith("]"):
            # Key: The first argument, specified `bot.tags[here]`
            key = clean_argument(self.buffer[self.index:])
            log.trace(f"Command mimicks getitem. Key: {key!r}")

            # note: if not key, this corresponds to an empty argument
            #       so this should throw / return a SyntaxError ?
            args = f'"{key}"'

            # Use the cog's `get` command.
            result = self.buffer[self.previous:self.index] + ".get"

        # Syntax is `bot.tags['ask'] = 'whatever'` => mimic `setattr`
        elif "=" in self.buffer and not self.buffer.endswith("="):
            equals_pos = self.buffer.find("=")

            # Key: The first argument, specified `bot.tags[here]`
            key = clean_argument(self.buffer[self.index:equals_pos])

            # Value: The second argument, specified after the `=`
            value = (
                clean_argument(
                    self.buffer.split("=")[1]
                )
                .replace("'", "\\'")  # escape any unescaped quotes
            )
            log.trace(f"Command mimicks setitem. Key: {key!r}, value: {value!r}.")

            # Use the cog's `set` command.
            result = self.buffer[self.previous:self.index] + ".set"
            args = f'"{key}" "{value}"'

        # Syntax is god knows what, pass it along
        # in the future, this should probably return / throw SyntaxError
        else:
            result = self.buffer
            args = ''
            log.trace(f"Command is of unknown syntax: {self.buffer}")

        # Reconstruct valid discord.py syntax
        self.buffer = f"{result} {args}"
        self.index = len(result)
        self.end = len(self.buffer)
        log.trace(f"Mimicked command: {self.buffer}")

    if isinstance(result, str):
        return result.lower()  # Case insensitivity, baby
    return result


# Monkey patch the methods
discord.ext.commands.view.StringView.skip_string = _skip_string
discord.ext.commands.view.StringView.get_word = _get_word
