# coding=utf-8
from discord.ext import commands
from discord.ext.commands import Context

from bot.constants import ADMIN_ROLE, MODERATOR_ROLE, VERIFICATION_CHANNEL, VERIFIED_ROLE

__author__ = "Gareth Coles"


def is_owner():
    async def predicate(ctx):
        return ctx.author.id == 316026178463072268
    return commands.check(predicate)


def is_admin():
    async def predicate(ctx: Context):
        for role in ctx.author.roles:
            if role.id == ADMIN_ROLE:
                return True
        return False
    return commands.check(predicate)


def is_moderator():
    async def predicate(ctx: Context):
        for role in ctx.author.roles:
            if role.id == MODERATOR_ROLE:
                return True
        return False
    return commands.check(predicate)


def is_verified():
    async def predicate(ctx: Context):
        for role in ctx.author.roles:
            if role.id == VERIFIED_ROLE:
                return True
        return False
    return commands.check(predicate)


def is_not_verified():
    async def predicate(ctx: Context):
        for role in ctx.author.roles:
            if role.id == VERIFIED_ROLE:
                return False
        return True
    return commands.check(predicate)


def is_in_verification_channel():
    async def predicate(ctx: Context):
        return ctx.channel.id == VERIFICATION_CHANNEL
    return commands.check(predicate)
