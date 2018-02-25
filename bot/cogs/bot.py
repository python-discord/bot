# coding=utf-8
import ast

from discord import Embed, Message
from discord.ext.commands import AutoShardedBot, Context, command, group

from dulwich.repo import Repo

from bot.constants import PYTHON_GUILD, VERIFIED_ROLE
from bot.decorators import with_role


class Bot:
    """
    Bot information commands
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    @group(invoke_without_command=True, name="bot", hidden=True)
    @with_role(VERIFIED_ROLE)
    async def bot_group(self, ctx: Context):
        """
        Bot informational commands
        """

        await ctx.invoke(self.bot.get_command("help"), "bot")

    @bot_group.command(aliases=["about"], hidden=True)
    @with_role(VERIFIED_ROLE)
    async def info(self, ctx: Context):
        """
        Get information about the bot
        """

        embed = Embed(
            description="A utility bot designed just for the Python server! Try `bot.help()` for more info.",
            url="https://github.com/discord-python/bot"
        )

        repo = Repo(".")
        sha = repo[repo.head()].sha().hexdigest()

        embed.add_field(name="Total Users", value=str(len(self.bot.get_guild(PYTHON_GUILD).members)))
        embed.add_field(name="Git SHA", value=str(sha)[:7])

        embed.set_author(
            name="Python Bot",
            url="https://github.com/discord-python/bot",
            icon_url="https://raw.githubusercontent.com/discord-python/branding/master/logos/logo_circle.png"
        )

        await ctx.send(embed=embed)

    @command(name="info()", aliases=["bot.info", "bot.about", "bot.about()", "info", "bot.info()"])
    @with_role(VERIFIED_ROLE)
    async def info_wrapper(self, ctx: Context):
        """
        Get information about the bot
        """

        await ctx.invoke(self.info)

    async def on_message(self, msg: Message):
        if msg.content.count("\n") >= 3:
            try:
                tree = ast.parse(msg.content)
                # Attempts to parse the message into an AST node.
                # Invalid Python code will raise a SyntaxError.
                if not all(isinstance(node, ast.Expr) for node in tree.body):
                    # we dont want multiple lines of single words,
                    # they would be syntactically valid Python but could also be
                    # just some random multiline text someone is sending.
                    formatted = f"```python\n{msg.content}\n```"
                    if len(formatted) <= 2000:
                        await msg.channel.send(formatted)
                        await bot.delete_message(msg)
            except SyntaxError:
                pass


def setup(bot):
    bot.add_cog(Bot(bot))
    print("Cog loaded: Bot")
