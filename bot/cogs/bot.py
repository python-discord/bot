# coding=utf-8
import ast
import re
import time

from discord import Embed, Message
from discord.ext.commands import AutoShardedBot, Context, command, group

from dulwich.repo import Repo

from bot.constants import (DEVTEST_CHANNEL, HELP1_CHANNEL, HELP2_CHANNEL,
                           HELP3_CHANNEL, PYTHON_CHANNEL, PYTHON_GUILD,
                           VERIFIED_ROLE)
from bot.decorators import with_role


class Bot:
    """
    Bot information commands
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

        # Stores allowed channels plus unix timestamp from last call
        self.channel_cooldowns = {HELP1_CHANNEL: 0,
                                  HELP2_CHANNEL: 0,
                                  HELP3_CHANNEL: 0,
                                  PYTHON_CHANNEL: 0,
                                  DEVTEST_CHANNEL: 0
        }  # noqa. E124

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

    def codeblock_stripping(self, msg: str):
        """
        Strip msg in order to find Python code.

        Tries to strip out Python code out of msg and returns the stripped block or
        None if the block is a valid Python codeblock.
        """
        if msg.count("\n") >= 3:
            # Filtering valid Python codeblocks and exiting if a valid Python codeblock is found
            if re.search("```(python|py)\n((?:.*\n*)+)```", msg, re.IGNORECASE):
                return None
            else:
                # Stripping backticks from every line of the message.
                content = ""
                for line in msg.splitlines():
                    content += line.strip("`") + "\n"

                content = content.strip()
                # Remove "Python" or "Py" from top of the message if exists
                if content.lower().startswith("python"):
                    content = content[6:]
                elif content.lower().startswith("py"):
                    content = content[2:]
                # Strip again to remove the whitespace(s) left before the code
                # If the msg looked like "Python <code>" before removing Python
                content = content.strip()
                return content

    async def on_message(self, msg: Message):
        if msg.channel.id in self.channel_cooldowns:
            on_cooldown = time.time() - self.channel_cooldowns[msg.channel.id] < 300
            if not on_cooldown or msg.channel.id == DEVTEST_CHANNEL:
                try:
                    # Attempts to parse the message into an AST node.
                    # Invalid Python code will raise a SyntaxError.
                    content = self.codeblock_stripping(msg.content)
                    if not content:
                        return

                    tree = ast.parse(content)

                    # Multiple lines of single words could be interpreted as expressions.
                    # This check is to avoid all nodes being parsed as expressions.
                    # (e.g. words over multiple lines)
                    if not all(isinstance(node, ast.Expr) for node in tree.body):
                        codeblock_tag = await self.bot.get_cog("Tags").get_tag_data("codeblock")
                        if codeblock_tag == {}:
                            # todo: add logging
                            return
                        howto = (f"Hey {msg.author.mention}!\n\nI noticed you were trying to paste code into this "
                                 f"channel.\n\n{codeblock_tag['tag_content']}")

                        howto_embed = Embed(description=howto)
                        await msg.channel.send(embed=howto_embed)
                        self.channel_cooldowns[msg.channel.id] = time.time()
                except SyntaxError:
                    pass


def setup(bot):
    bot.add_cog(Bot(bot))
    print("Cog loaded: Bot")
