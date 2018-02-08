# coding=utf-8
import discord.ext.commands.view


def case_insensitive_skip_string(self, string: str):
    """Invokes the skip_string method from
    discord.ext.commands.view used to find
    the prefix in a message, but allows prefix
    to ignore case sensitivity
    """
    string = string.lower()
    return _skip_string(self, string)


def case_insensitive_get_word(self):
    """Invokes the get_word method from
    discord.ext.commands.view used to find
    the bot command part of a message, but
    allows the command to ignore case sensitivity
    """
    word = _get_word(self)
    if isinstance(word, str):
        return word.lower()
    return word


# save the old methods
_skip_string = discord.ext.commands.view.skip_string
_get_word = discord.ext.commands.view.get_word

# monkey patch them to be case insensitive
discord.ext.commands.view.skip_string = case_insensitive_skip_string
discord.ext.commands.view.get_word = case_insensitive_get_word
