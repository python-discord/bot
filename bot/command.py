from discord.ext import commands


class Command(commands.Command):
    """
    A `discord.ext.commands.Command` subclass which supports root aliases.

    A `root_aliases` keyword argument is added, which is a sequence of alias names that will act as
    top-level commands rather than being aliases of the command's group. It's stored as an attribute
    also named `root_aliases`.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.root_aliases = kwargs.get("root_aliases", [])

        if not isinstance(self.root_aliases, (list, tuple)):
            raise TypeError("Root aliases of a command must be a list or a tuple of strings.")
