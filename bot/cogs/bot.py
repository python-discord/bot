import ast
import logging
import re
import time
from typing import Optional, Tuple

from discord import Embed, Message, RawMessageUpdateEvent, TextChannel
from discord.ext.commands import Cog, Context, command, group

from bot.bot import Bot
from bot.cogs.token_remover import TokenRemover
from bot.constants import Categories, Channels, DEBUG_MODE, Guild, MODERATION_ROLES, Roles, URLs
from bot.decorators import with_role
from bot.utils.messages import wait_for_deletion

log = logging.getLogger(__name__)

RE_MARKDOWN = re.compile(r'([*_~`|>])')


class BotCog(Cog, name="Bot"):
    """Bot information commands."""

    def __init__(self, bot: Bot):
        self.bot = bot

        # Stores allowed channels plus epoch time since last call.
        self.channel_cooldowns = {
            Channels.python_discussion: 0,
        }

        # These channels will also work, but will not be subject to cooldown
        self.channel_whitelist = (
            Channels.bot_commands,
        )

        # Stores improperly formatted Python codeblock message ids and the corresponding bot message
        self.codeblock_message_ids = {}

    @group(invoke_without_command=True, name="bot", hidden=True)
    @with_role(Roles.verified)
    async def botinfo_group(self, ctx: Context) -> None:
        """Bot informational commands."""
        await ctx.invoke(self.bot.get_command("help"), "bot")

    @botinfo_group.command(name='about', aliases=('info',), hidden=True)
    @with_role(Roles.verified)
    async def about_command(self, ctx: Context) -> None:
        """Get information about the bot."""
        embed = Embed(
            description="A utility bot designed just for the Python server! Try `!help` for more info.",
            url="https://github.com/python-discord/bot"
        )

        embed.add_field(name="Total Users", value=str(len(self.bot.get_guild(Guild.id).members)))
        embed.set_author(
            name="Python Bot",
            url="https://github.com/python-discord/bot",
            icon_url=URLs.bot_avatar
        )

        log.info(f"{ctx.author} called !about. Returning information about the bot.")
        await ctx.send(embed=embed)

    @command(name='echo', aliases=('print',))
    @with_role(*MODERATION_ROLES)
    async def echo_command(self, ctx: Context, channel: Optional[TextChannel], *, text: str) -> None:
        """Repeat the given message in either a specified channel or the current channel."""
        if channel is None:
            await ctx.send(text)
        else:
            await channel.send(text)

    @command(name='embed')
    @with_role(*MODERATION_ROLES)
    async def embed_command(self, ctx: Context, *, text: str) -> None:
        """Send the input within an embed to the current channel."""
        embed = Embed(description=text)
        await ctx.send(embed=embed)

    def codeblock_stripping(self, msg: str, bad_ticks: bool) -> Optional[Tuple[Tuple[str, ...], str]]:
        """
        Strip msg in order to find Python code.

        Tries to strip out Python code out of msg and returns the stripped block or
        None if the block is a valid Python codeblock.
        """
        if msg.count("\n") >= 3:
            # Filtering valid Python codeblocks and exiting if a valid Python codeblock is found.
            if re.search("```(?:py|python)\n(.*?)```", msg, re.IGNORECASE | re.DOTALL) and not bad_ticks:
                log.trace(
                    "Someone wrote a message that was already a "
                    "valid Python syntax highlighted code block. No action taken."
                )
                return None

            else:
                # Stripping backticks from every line of the message.
                log.trace(f"Stripping backticks from message.\n\n{msg}\n\n")
                content = ""
                for line in msg.splitlines(keepends=True):
                    content += line.strip("`")

                content = content.strip()

                # Remove "Python" or "Py" from start of the message if it exists.
                log.trace(f"Removing 'py' or 'python' from message.\n\n{content}\n\n")
                pycode = False
                if content.lower().startswith("python"):
                    content = content[6:]
                    pycode = True
                elif content.lower().startswith("py"):
                    content = content[2:]
                    pycode = True

                if pycode:
                    content = content.splitlines(keepends=True)

                    # Check if there might be code in the first line, and preserve it.
                    first_line = content[0]
                    if " " in content[0]:
                        first_space = first_line.index(" ")
                        content[0] = first_line[first_space:]
                        content = "".join(content)

                    # If there's no code we can just get rid of the first line.
                    else:
                        content = "".join(content[1:])

                # Strip it again to remove any leading whitespace. This is neccessary
                # if the first line of the message looked like ```python <code>
                old = content.strip()

                # Strips REPL code out of the message if there is any.
                content, repl_code = self.repl_stripping(old)
                if old != content:
                    return (content, old), repl_code

                # Try to apply indentation fixes to the code.
                content = self.fix_indentation(content)

                # Check if the code contains backticks, if it does ignore the message.
                if "`" in content:
                    log.trace("Detected ` inside the code, won't reply")
                    return None
                else:
                    log.trace(f"Returning message.\n\n{content}\n\n")
                    return (content,), repl_code

    def fix_indentation(self, msg: str) -> str:
        """Attempts to fix badly indented code."""
        def unindent(code: str, skip_spaces: int = 0) -> str:
            """Unindents all code down to the number of spaces given in skip_spaces."""
            final = ""
            current = code[0]
            leading_spaces = 0

            # Get numbers of spaces before code in the first line.
            while current == " ":
                current = code[leading_spaces + 1]
                leading_spaces += 1
            leading_spaces -= skip_spaces

            # If there are any, remove that number of spaces from every line.
            if leading_spaces > 0:
                for line in code.splitlines(keepends=True):
                    line = line[leading_spaces:]
                    final += line
                return final
            else:
                return code

        # Apply fix for "all lines are overindented" case.
        msg = unindent(msg)

        # If the first line does not end with a colon, we can be
        # certain the next line will be on the same indentation level.
        #
        # If it does end with a colon, we will need to indent all successive
        # lines one additional level.
        first_line = msg.splitlines()[0]
        code = "".join(msg.splitlines(keepends=True)[1:])
        if not first_line.endswith(":"):
            msg = f"{first_line}\n{unindent(code)}"
        else:
            msg = f"{first_line}\n{unindent(code, 4)}"
        return msg

    def repl_stripping(self, msg: str) -> Tuple[str, bool]:
        """
        Strip msg in order to extract Python code out of REPL output.

        Tries to strip out REPL Python code out of msg and returns the stripped msg.

        Returns True for the boolean if REPL code was found in the input msg.
        """
        final = ""
        for line in msg.splitlines(keepends=True):
            if line.startswith(">>>") or line.startswith("..."):
                final += line[4:]
        log.trace(f"Formatted: \n\n{msg}\n\n to \n\n{final}\n\n")
        if not final:
            log.trace(f"Found no REPL code in \n\n{msg}\n\n")
            return msg, False
        else:
            log.trace(f"Found REPL code in \n\n{msg}\n\n")
            return final.rstrip(), True

    def has_bad_ticks(self, msg: Message) -> bool:
        """Check to see if msg contains ticks that aren't '`'."""
        not_backticks = [
            "'''", '"""', "\u00b4\u00b4\u00b4", "\u2018\u2018\u2018", "\u2019\u2019\u2019",
            "\u2032\u2032\u2032", "\u201c\u201c\u201c", "\u201d\u201d\u201d", "\u2033\u2033\u2033",
            "\u3003\u3003\u3003"
        ]

        return msg.content[:3] in not_backticks

    @Cog.listener()
    async def on_message(self, msg: Message) -> None:
        """
        Detect poorly formatted Python code in new messages.

        If poorly formatted code is detected, send the user a helpful message explaining how to do
        properly formatted Python syntax highlighting codeblocks.
        """
        is_help_channel = (
            msg.channel.category
            and msg.channel.category.id in (Categories.help_available, Categories.help_in_use)
        )
        parse_codeblock = (
            (
                is_help_channel
                or msg.channel.id in self.channel_cooldowns
                or msg.channel.id in self.channel_whitelist
            )
            and not msg.author.bot
            and len(msg.content.splitlines()) > 3
            and not TokenRemover.is_token_in_message(msg)
        )

        if parse_codeblock:  # no token in the msg
            on_cooldown = (time.time() - self.channel_cooldowns.get(msg.channel.id, 0)) < 300
            if not on_cooldown or DEBUG_MODE:
                try:
                    if self.has_bad_ticks(msg):
                        ticks = msg.content[:3]
                        content = self.codeblock_stripping(f"```{msg.content[3:-3]}```", True)
                        if content is None:
                            return

                        content, repl_code = content

                        if len(content) == 2:
                            content = content[1]
                        else:
                            content = content[0]

                        space_left = 204
                        if len(content) >= space_left:
                            current_length = 0
                            lines_walked = 0
                            for line in content.splitlines(keepends=True):
                                if current_length + len(line) > space_left or lines_walked == 10:
                                    break
                                current_length += len(line)
                                lines_walked += 1
                            content = content[:current_length] + "#..."
                        content_escaped_markdown = RE_MARKDOWN.sub(r'\\\1', content)
                        howto = (
                            "It looks like you are trying to paste code into this channel.\n\n"
                            "You seem to be using the wrong symbols to indicate where the codeblock should start. "
                            f"The correct symbols would be \\`\\`\\`, not `{ticks}`.\n\n"
                            "**Here is an example of how it should look:**\n"
                            f"\\`\\`\\`python\n{content_escaped_markdown}\n\\`\\`\\`\n\n"
                            "**This will result in the following:**\n"
                            f"```python\n{content}\n```"
                        )

                    else:
                        howto = ""
                        content = self.codeblock_stripping(msg.content, False)
                        if content is None:
                            return

                        content, repl_code = content
                        # Attempts to parse the message into an AST node.
                        # Invalid Python code will raise a SyntaxError.
                        tree = ast.parse(content[0])

                        # Multiple lines of single words could be interpreted as expressions.
                        # This check is to avoid all nodes being parsed as expressions.
                        # (e.g. words over multiple lines)
                        if not all(isinstance(node, ast.Expr) for node in tree.body) or repl_code:
                            # Shorten the code to 10 lines and/or 204 characters.
                            space_left = 204
                            if content and repl_code:
                                content = content[1]
                            else:
                                content = content[0]

                            if len(content) >= space_left:
                                current_length = 0
                                lines_walked = 0
                                for line in content.splitlines(keepends=True):
                                    if current_length + len(line) > space_left or lines_walked == 10:
                                        break
                                    current_length += len(line)
                                    lines_walked += 1
                                content = content[:current_length] + "#..."

                            content_escaped_markdown = RE_MARKDOWN.sub(r'\\\1', content)
                            howto += (
                                "It looks like you're trying to paste code into this channel.\n\n"
                                "Discord has support for Markdown, which allows you to post code with full "
                                "syntax highlighting. Please use these whenever you paste code, as this "
                                "helps improve the legibility and makes it easier for us to help you.\n\n"
                                f"**To do this, use the following method:**\n"
                                f"\\`\\`\\`python\n{content_escaped_markdown}\n\\`\\`\\`\n\n"
                                "**This will result in the following:**\n"
                                f"```python\n{content}\n```"
                            )

                            log.debug(f"{msg.author} posted something that needed to be put inside python code "
                                      "blocks. Sending the user some instructions.")
                        else:
                            log.trace("The code consists only of expressions, not sending instructions")

                    if howto != "":
                        howto_embed = Embed(description=howto)
                        bot_message = await msg.channel.send(f"Hey {msg.author.mention}!", embed=howto_embed)
                        self.codeblock_message_ids[msg.id] = bot_message.id

                        self.bot.loop.create_task(
                            wait_for_deletion(bot_message, user_ids=(msg.author.id,), client=self.bot)
                        )
                    else:
                        return

                    if msg.channel.id not in self.channel_whitelist:
                        self.channel_cooldowns[msg.channel.id] = time.time()

                except SyntaxError:
                    log.trace(
                        f"{msg.author} posted in a help channel, and when we tried to parse it as Python code, "
                        "ast.parse raised a SyntaxError. This probably just means it wasn't Python code. "
                        f"The message that was posted was:\n\n{msg.content}\n\n"
                    )

    @Cog.listener()
    async def on_raw_message_edit(self, payload: RawMessageUpdateEvent) -> None:
        """Check to see if an edited message (previously called out) still contains poorly formatted code."""
        if (
            # Checks to see if the message was called out by the bot
            payload.message_id not in self.codeblock_message_ids
            # Makes sure that there is content in the message
            or payload.data.get("content") is None
            # Makes sure there's a channel id in the message payload
            or payload.data.get("channel_id") is None
        ):
            return

        # Retrieve channel and message objects for use later
        channel = self.bot.get_channel(int(payload.data.get("channel_id")))
        user_message = await channel.fetch_message(payload.message_id)

        #  Checks to see if the user has corrected their codeblock.  If it's fixed, has_fixed_codeblock will be None
        has_fixed_codeblock = self.codeblock_stripping(payload.data.get("content"), self.has_bad_ticks(user_message))

        # If the message is fixed, delete the bot message and the entry from the id dictionary
        if has_fixed_codeblock is None:
            bot_message = await channel.fetch_message(self.codeblock_message_ids[payload.message_id])
            await bot_message.delete()
            del self.codeblock_message_ids[payload.message_id]
            log.trace("User's incorrect code block has been fixed. Removing bot formatting message.")


def setup(bot: Bot) -> None:
    """Load the Bot cog."""
    bot.add_cog(BotCog(bot))
