# coding=utf-8
import re

import discord.ext.commands.view


def case_insensitive_skip_string(self, string: str) -> bool:
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


def case_insensitive_get_word(self) -> str:
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

    # This unholy regex splits the string by commas that are outside quotes
    split_outside_quotes = r'(?:[^\s,\"\']|[\"\'](?:\\.|[^\"\'])*[\'\"])+'
    new_args = re.findall(split_outside_quotes, self.buffer[self.index:])

    # if the len is 0, we're just calling bot.tags() or something
    if len(new_args) > 0:
        new_args = " ".join(new_args)  # Replace those commas with spaces
        new_args = new_args.replace("(", "").replace(")", "")  # remove the ()'s
        new_args = new_args.replace("'", "\"")  # d.py doesn't like single quotes

        # We've changed the command from `tags("a", "b, c, d")` into `tags "a" "b, c, d"`
        self.buffer = f"{self.buffer[:self.index]} {new_args}"
        self.end = len(self.buffer)  # reset the end now that we've removed characters.

    if isinstance(result, str):
        return result.lower()  # Case insensitivity, baby
    return result


# Monkey patch them to be case insensitive
discord.ext.commands.view.StringView.skip_string = case_insensitive_skip_string
discord.ext.commands.view.StringView.get_word = case_insensitive_get_word
