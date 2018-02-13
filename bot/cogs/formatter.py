# coding=utf-8
from discord.ext.commands import HelpFormatter, Paginator

class Formatter(HelpFormatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    