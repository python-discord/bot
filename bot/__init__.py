import ast
import logging
import re
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
    """

    def parse_python(view_pos):
        """
        Takes the instance of the view and parses the buffer, if it contains valid python syntax.
        This may fail spectacularly with a SyntaxError, which must be caught by the caller.

        Example of valid Python syntax calls:
        ------------------------------
        bot.tags.set("test", 'a dark, dark night')
        bot.help(tags.delete)
        bot.hELP(tags.delete)
        bot.tags['internet']
        bot.tags['internet'] = "A series of tubes"

        :return: the parsed command
        """

        # Check what's after the '('
        next_char = None
        if len(self.buffer) != self.index:
            next_char = self.buffer[self.index + 1]

        # Conditions for a valid, parsable command.
        python_parse_conditions = (
            current == "("
            and next_char
            and next_char != ")"
        )

        # Catch raw channel, member or role mentions and wrap them in quotes.
        self.buffer = re.sub(r"(<(?:@|@!|[#&])\d+>)",
                             r'"\1"',
                             self.buffer)

        # Let's parse!
        python_result = None

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

        elif current == "(" and next_char == ")":
            # Move the cursor to capture the ()'s
            log.debug("User called command without providing arguments.")
            view_pos += 2
            python_result = self.buffer[self.previous:self.index + (pos+2)]
            self.index += 2

        # Check if a command in the form of `bot.tags['ask']`
        # or alternatively `bot.tags['ask'] = 'whatever'` was used.
        elif current == "[":
            log.trace(f"Got a command candidate for getitem / setitem mimick: {self.buffer}")
            # Syntax is `bot.tags['ask']` => mimic `getattr`
            if self.buffer.endswith("]"):
                # Key: The first argument, specified `bot.tags[here]`
                key = self.buffer[self.index + 1:self.buffer.rfind("]")]
                log.trace(f"Command mimicks getitem. Key: {key!r}")

                # note: if not key, this corresponds to an empty argument
                #       so this should throw / return a SyntaxError ?
                args = ast.literal_eval(key)

                # Use the cog's `get` command.
                python_result = self.buffer[self.previous:self.index] + ".get"

            # Syntax is `bot.tags['ask'] = 'whatever'` => mimic `setattr`
            elif "=" in self.buffer and not self.buffer.endswith("="):
                equals_pos = self.buffer.find("=")
                closing_bracket_pos = self.buffer.rfind("]", 0, equals_pos)

                # Key: The first argument, specified `bot.tags[here]`
                key_contents = self.buffer[self.index + 1:closing_bracket_pos]
                key = ast.literal_eval(key_contents)

                # Value: The second argument, specified after the `=`
                right_hand = self.buffer.split("=", maxsplit=1)[1].strip()
                value = ast.literal_eval(right_hand)

                # If the value is a falsy value - mimick `bot.tags.delete(key)`
                if not value:
                    log.trace(f"Command mimicks delitem. Key: {key!r}.")
                    python_result = self.buffer[self.previous:self.index] + ".delete"
                    args = key

                # Otherwise, assume assignment, for example `bot.tags['this'] = 'that'`
                else:
                    # Allow using double quotes in triple double quote string
                    value = value.replace('"', '\\"')
                    log.trace(f"Command mimicks setitem. Key: {key!r}, value: {value!r}.")

                    # Use the cog's `set` command.
                    python_result = self.buffer[self.previous:self.index] + ".set"
                    args = f'"{key}" "{value}"'

            # Syntax is god knows what, pass it along
            # in the future, this should probably return / throw SyntaxError
            else:
                python_result = self.buffer
                args = ''
                log.trace(f"Command is of unknown syntax: {self.buffer}")

            # Reconstruct valid discord.py syntax
            self.buffer = f"{result} {args}"
            self.index = len(result)
            self.end = len(self.buffer)
            log.trace(f"Mimicked command: {self.buffer}")

        return python_result

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

    # If the command looks like a python syntax command, try to parse it.
    if current == "(" or current == "[":
        try:
            python_result = parse_python(pos)
            if python_result:
                result = python_result

        except SyntaxError:
            log.debug(
                "A SyntaxError was encountered while parsing a python-syntaxed command:"
                "\nTraceback (most recent call last):\n"
                '  File "<stdin>", line 1, in <module>\n'
                f"    {self.buffer}\n"
                f"     {' ' * self.index}^\n"
                f"SyntaxError: invalid syntax\n"
            )
            return

        except ValueError:
            log.debug(
                "A ValueError was encountered while parsing a python-syntaxed command:"
                "\nTraceback (most recent call last):\n"
                '  File "<stdin>", line 1, in <module>\n'
                f"ValueError: could not ast.literal_eval the following: '{self.buffer}'"
            )
            return

    return result


# Monkey patch the methods
discord.ext.commands.view.StringView.skip_string = _skip_string
discord.ext.commands.view.StringView.get_word = _get_word
