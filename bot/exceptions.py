from discord.ext.commands import BadArgument


class CogBadArgument(BadArgument):
    """
    A custom `BadArgument` subclass that can be used for
    setting up custom error handlers on a per-command
    basis in cogs. The standard `on_command_error` handler
    ignores any exceptions of this type.
    """
