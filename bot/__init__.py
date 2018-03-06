# coding=utf-8
import ast

import discord.ext.commands.view


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
            if current.isspace() or current == "(":
                break
            pos += 1
        except IndexError:
            break

    self.previous = self.index
    result = self.buffer[self.index:self.index + pos]
    self.index += pos

    if current == "(" and self.buffer[self.index + 1] != ")":

        # Parse the args
        args = self.buffer[self.index:]
        args = ast.literal_eval(args)

        # Force args into container
        if isinstance(args, str):
            args = (args,)

        # Type validate and format
        new_args = []
        for arg in args:

            # Other types get converted to strings
            if not isinstance(arg, str):
                arg = str(arg)

            # Adding double quotes to every argument
            new_args.append(f'"{arg}"')

        new_args = " ".join(new_args)
        self.buffer = f"{self.buffer[:self.index]} {new_args}"
        self.end = len(self.buffer)  # Recalibrate the end since we've removed commas

    else:
        # Move the cursor to capture the ()'s
        pos += 2
        result = self.buffer[self.previous:self.index + (pos+2)]
        self.index += 2

    if isinstance(result, str):
        return result.lower()  # Case insensitivity, baby
    return result


# Monkey patch the methods
discord.ext.commands.view.StringView.skip_string = _skip_string
discord.ext.commands.view.StringView.get_word = _get_word
