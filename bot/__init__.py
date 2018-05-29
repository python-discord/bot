import ast
import logging
import re
import sys
from logging import Logger, StreamHandler
from logging.handlers import SysLogHandler

import discord.ext.commands.view
from logmatic import JsonFormatter

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

# We need to defer the import from `constants.py`
# because otherwise the logging config would not be applied
# to any logging done in the module.
from bot.constants import Papertrail  # noqa
if Papertrail.address:
    papertrail_handler = SysLogHandler(address=(Papertrail.address, Papertrail.port))
    papertrail_handler.setLevel(logging.DEBUG)
    logging.getLogger('bot').addHandler(papertrail_handler)


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

    def parse_python(buffer_pos):
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

        # Check what's after the '(' or '['
        next_char = None
        if len(self.buffer) - 1 != self.index:
            next_char = self.buffer[self.index + 1]

        # Catch raw channel, member or role mentions and wrap them in quotes.
        tempbuffer = self.buffer
        tempbuffer = re.sub(r"(<(?:@|@!|[#&])\d+>)",
                            r'"\1"',
                            tempbuffer)

        # Let's parse!
        log.debug("A python-style command was used. Attempting to parse. "
                  f"Buffer is '{self.buffer}'. Tempbuffer is '{tempbuffer}'. "
                  "A step-by-step can be found in the trace log.")

        if current == "(" and next_char == ")":
            # Move the cursor to capture the ()'s
            log.debug("User called command without providing arguments.")
            buffer_pos += 2
            parsed_result = self.buffer[self.previous:self.index + (buffer_pos+2)]
            self.index += 2
            return parsed_result

        elif current == "(" and next_char:

            # Parse the args
            log.trace(f"Parsing command with ast.literal_eval. args are {tempbuffer[self.index:]}")
            args = tempbuffer[self.index:]
            args = ast.literal_eval(args)

            # Return what we'd return for a non-python syntax call
            log.trace(f"Returning {self.buffer[self.previous:self.index]}")
            parsed_result = self.buffer[self.previous:self.index]

        elif current == "(" or current == "[" and not next_char:

            # Just remove the start bracket
            log.debug("User called command with a single bracket. Removing bracket.")
            parsed_result = self.buffer[self.previous:self.index]
            args = None

        # Check if a command in the form of `bot.tags['ask']`
        # or alternatively `bot.tags['ask'] = 'whatever'` was used.
        elif current == "[":

            # Syntax is `bot.tags['ask']` => mimic `getattr`
            log.trace(f"Got a command candidate for getitem / setitem parsing: {self.buffer}")
            if self.buffer.endswith("]"):

                # Key: The first argument, specified `bot.tags[here]`
                key = tempbuffer[self.index + 1:tempbuffer.rfind("]")]
                log.trace(f"Command mimicks getitem. Key: {key!r}")
                args = ast.literal_eval(key)

                # Use the cogs `.get` method.
                parsed_result = self.buffer[self.previous:self.index] + ".get"

            # Syntax is `bot.tags['ask'] = 'whatever'` => mimic `setattr`
            elif "=" in self.buffer and not self.buffer.endswith("="):
                equals_pos = tempbuffer.find("=")
                closing_bracket_pos = tempbuffer.rfind("]", 0, equals_pos)

                # Key: The first argument, specified `bot.tags[here]`
                key_contents = tempbuffer[self.index + 1:closing_bracket_pos]
                key = ast.literal_eval(key_contents)

                # Value: The second argument, specified after the `=`
                right_hand = tempbuffer.split("=", maxsplit=1)[1].strip()
                value = ast.literal_eval(right_hand)

                # If the value is a falsy value - mimick `bot.tags.delete(key)`
                if not value:
                    log.trace(f"Command mimicks delitem. Key: {key!r}.")
                    parsed_result = self.buffer[self.previous:self.index] + ".delete"
                    args = key

                # Otherwise, assume assignment, for example `bot.tags['this'] = 'that'`
                else:
                    log.trace(f"Command mimicks setitem. Key: {key!r}, value: {value!r}.")
                    parsed_result = self.buffer[self.previous:self.index] + ".set"
                    args = (key, value)

            # Syntax is god knows what, pass it along
            else:
                parsed_result = self.buffer
                args = ''
                log.trace(f"Command is of unknown syntax: {self.buffer}")

        # Args handling
        new_args = []

        if args:
            # Force args into container
            if not isinstance(args, tuple):
                args = (args,)

            # Type validate and format
            for arg in args:

                # Other types get converted to strings
                if not isinstance(arg, str):
                    log.trace(f"{arg} is not a str, casting to str.")
                    arg = str(arg)

                # Allow using double quotes within triple double quotes
                arg = arg.replace('"', '\\"')

                # Adding double quotes to every argument
                log.trace("Wrapping all args in double quotes.")
                new_args.append(f'"{arg}"')

        # Reconstruct valid discord.py syntax
        prefix = self.buffer[:self.previous]
        self.buffer = f"{prefix}{parsed_result}"

        if new_args:
            self.buffer += (" " + " ".join(new_args))

        self.index = len(f"{prefix}{parsed_result}")
        self.end = len(self.buffer)
        log.trace(f"Modified the buffer. New buffer is now '{self.buffer}'")

        return parsed_result

    # Iterate through the buffer and determine
    pos = 0
    current = None
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
            result = parse_python(pos)

        except SyntaxError:
            log.debug(
                "A SyntaxError was encountered while parsing a python-syntaxed command:"
                "\nTraceback (most recent call last):\n"
                '  File "<stdin>", line 1, in <module>\n'
                f"    {self.buffer}\n"
                f"     {' ' * self.index}^\n"
                "SyntaxError: invalid syntax"
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
