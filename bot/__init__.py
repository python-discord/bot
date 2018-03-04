# coding=utf-8
import discord.ext.commands.view
import discord.ext.commands.formatter


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
    allows the command to ignore case sensitivity
    """

    word = _get_word(self)
    if isinstance(word, str):
        return word.lower()
    return word


def init_max_lines(self, prefix='```', suffix='```',
                   max_size=2000, max_lines=10):
    """
    This function overrides the Paginator.__init__
    from inside discord.ext.commands.
    It overrides in order to allow us to configure
    the maximum number of lines per page.
    """
    self.prefix = prefix
    self.suffix = suffix
    self.max_size = max_size - len(suffix)
    self.max_lines = max_lines
    self._current_page = [prefix]
    self._linecount = 0
    self._count = len(prefix) + 1  # prefix + newline
    self._pages = []


def add_max_lines(self, line='', *, empty=False):
    """Adds a line to the current page.

    If the line exceeds the :attr:`max_size` then an exception
    is raised.

    This function overrides the Paginator.add_lines
    from inside discord.ext.commands.
    It overrides in order to allow us to configure
    the maximum number of lines per page.

    Parameters
    -----------
    line: str
        The line to add.
    empty: bool
        Indicates if another empty line should be added.

    Raises
    ------
    RuntimeError
        The line was too big for the current :attr:`max_size`.
    """
    if len(line) > self.max_size - len(self.prefix) - 2:
        raise RuntimeError('Line exceeds maximum page size %s' % (self.max_size - len(self.prefix) - 2))

    if self._count + len(line) + 1 > self.max_size:
        self.close_page()

    if self._linecount >= self.max_lines:
        self._linecount = 0
        self.close_page()

    self._linecount += 1

    self._count += len(line) + 1
    self._current_page.append(line)

    if empty:
        self._current_page.append('')
        self._count += 1


# Save the old methods
_skip_string = discord.ext.commands.view.StringView.skip_string
_get_word = discord.ext.commands.view.StringView.get_word

# Monkey patching prefixes and commands to be case insensitive
discord.ext.commands.view.StringView.skip_string = case_insensitive_skip_string
discord.ext.commands.view.StringView.get_word = case_insensitive_get_word

# Monkey patching paginator to add max_lines
discord.ext.commands.formatter.Paginator.__init__ = init_max_lines
discord.ext.commands.formatter.Paginator.add_line = add_max_lines
