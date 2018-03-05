# coding=utf-8
import re

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

    # get all single and double quote encased args
    single_quotes = r'[\']([^\']*?)[\']'
    double_quotes = r'[\"]([^\"]*?)[\"]'

    # start with the type of quote that occurs first
    buf = self.buffer[self.index:]

    # single quotes occur first
    if (buf.find("'") < buf.find('"')) and buf.find("'") != -1:
        first = single_quotes
        second = double_quotes
    # double quotes occur first
    else:
        first = double_quotes
        second = single_quotes

    # after we get the first arg, we remove it from the buf so that
    # quotes inside the arg will not be picked up in the second findall.
    new_args = re.findall(first, buf)
    print(new_args)
    for arg in new_args:
        buf = buf.replace(arg, "")
    new_args += re.findall(second, buf)
    print(new_args)

    if len(new_args) > 0:
        reformatted_args = []

        for arg in new_args:
            arg = arg.strip("()\"\'")  # Remove (), ' and " from start and end
            reformatted_args.append(f'"{arg}"')  # Surround by double quotes instead

        # We've changed the command from `tags("a", 'b, c, d')` into `tags "a" "b, c, d"`
        new_args = " ".join(reformatted_args)
        self.buffer = f"{self.buffer[:self.index]} {new_args}"  # Put a space between command and args in the buffer
        self.end = len(self.buffer)  # reset the end now that we've removed characters.

    # if the len is 0, we're calling bot.command() without args
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
