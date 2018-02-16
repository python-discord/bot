# coding=utf-8
from discord.ext import commands
from discord.ext.commands import Context


def invoke_with_prefix(prefix: str) -> commands.check:
    '''Allow a command to only be invoked with one prefix
    :str: prefix - The prefix to be triggered with
    '''
    async def predicate(ctx: Context):
        return ctx.prefix == prefix
    return commands.check(predicate)


def with_role(*role_ids: int):
    async def predicate(ctx: Context):
        if not ctx.guild:  # Return False in a DM
            return False

        return any((role.id in role_ids) for role in ctx.author.roles)
    return commands.check(predicate)


def without_role(*role_ids: int):
    async def predicate(ctx: Context):
        if not ctx.guild:  # Return False in a DM
            return False

        author_roles = [role.id for role in ctx.author.roles]
        return all(role not in author_roles for role in role_ids)
    return commands.check(predicate)


def in_channel(channel_id):
    async def predicate(ctx: Context):
        return ctx.channel.id == channel_id
    return commands.check(predicate)
