# coding=utf-8
import ast
import time

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
        self.code_block_channels = {303906576991780866: 0, 303906556754395136: 0, 303906514266226689: 0, 267624335836053506: 0}
        # stores allowed channels plus unix timestmp from last call

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
        if msg.channel.id in self.code_block_channels:
            if self.allowed[msg.channel.id]-time.time() > 300:
                if msg.content.count("\n") >= 3:
                    try:
                        tree = ast.parse(msg.content)

                        # Attempts to parse the message into an AST node.
                        # Invalid Python code will raise a SyntaxError.
                        if not all(isinstance(node, ast.Expr) for node in tree.body):

                            # We don't want multiple lines of single words,
                            # They would be syntactically valid Python but could also be
                            # Just some random multiline text someone is sending.
                            howto = """Please use syntax highlighted blocks, as it makes it more legible for other users.

To do this, you should input your content like this:

\`\`\`python
print("Hello world!")
\`\`\`

This will result in the following:
```
print("Hello world!")
```
"""
                            information = Embed(title="Code formatting", description=howto)
                            await msg.channel.send(embed=information)
                            self.code_block_channels[msg.channel.id] = time.time()
                    except SyntaxError:
                        pass


def setup(bot):
    bot.add_cog(Bot(bot))
    print("Cog loaded: Bot")
