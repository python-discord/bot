import ast
import logging
import re
import time
from typing import NamedTuple, Optional, Sequence, Tuple

import discord
from discord import Embed, Message, RawMessageUpdateEvent
from discord.ext.commands import Bot, Cog

from bot.cogs.token_remover import TokenRemover
from bot.constants import Categories, Channels, DEBUG_MODE
from bot.utils.messages import wait_for_deletion

log = logging.getLogger(__name__)

RE_MARKDOWN = re.compile(r'([*_~`|>])')
RE_CODE_BLOCK_LANGUAGE = re.compile(r"```(?:[^\W_]+)\n(.*?)```", re.DOTALL)
BACKTICK = "`"
TICKS = {
    BACKTICK,
    "'",
    '"',
    "\u00b4",  # ACUTE ACCENT
    "\u2018",  # LEFT SINGLE QUOTATION MARK
    "\u2019",  # RIGHT SINGLE QUOTATION MARK
    "\u2032",  # PRIME
    "\u201c",  # LEFT DOUBLE QUOTATION MARK
    "\u201d",  # RIGHT DOUBLE QUOTATION MARK
    "\u2033",  # DOUBLE PRIME
    "\u3003",  # VERTICAL KANA REPEAT MARK UPPER HALF
}
RE_CODE_BLOCK = re.compile(
    fr"""
    (
        ([{''.join(TICKS)}])  # Put all ticks into a character class within a group.
        \2{{2}}               # Match the previous group 2 more times to ensure it's the same char.
    )
    ([^\W_]+\n)?              # Optionally match a language specifier followed by a newline.
    (.+?)                     # Match the actual code within the block.
    \1                        # Match the same 3 ticks used at the start of the block.
    """,
    re.DOTALL | re.VERBOSE
)


class CodeBlock(NamedTuple):
    """Represents a Markdown code block."""

    content: str
    language: str
    tick: str


class CodeBlockCog(Cog, name="Code Block"):
    """Detect improperly formatted code blocks and suggest proper formatting."""

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

    def codeblock_stripping(self, msg: str, bad_ticks: bool) -> Optional[Tuple[Tuple[str, ...], str]]:
        """
        Strip msg in order to find Python code.

        Tries to strip out Python code out of msg and returns the stripped block or
        None if the block is a valid Python codeblock.
        """
        if len(msg.split("\n", 3)) <= 3:
            return None

        # Filtering valid Python codeblocks and exiting if a valid Python codeblock is found.
        if RE_CODE_BLOCK_LANGUAGE.search(msg) and not bad_ticks:
            log.trace("Code block already has valid syntax highlighting; no action taken")
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

    def format_bad_ticks_message(self, message: discord.Message) -> Optional[str]:
        """Return the guide message to output for bad code block ticks in `message`."""
        ticks = message.content[:3]
        content = self.codeblock_stripping(f"```{message.content[3:-3]}```", True)
        if content is None:
            return

        content, repl_code = content

        if len(content) == 2:
            content = content[1]
        else:
            content = content[0]

        content = self.truncate(content)
        content_escaped_markdown = RE_MARKDOWN.sub(r'\\\1', content)

        return (
            "It looks like you are trying to paste code into this channel.\n\n"
            "You seem to be using the wrong symbols to indicate where the codeblock should start. "
            f"The correct symbols would be \\`\\`\\`, not `{ticks}`.\n\n"
            "**Here is an example of how it should look:**\n"
            f"\\`\\`\\`python\n{content_escaped_markdown}\n\\`\\`\\`\n\n"
            "**This will result in the following:**\n"
            f"```python\n{content}\n```"
        )

    def format_guide_message(self, message: discord.Message) -> Optional[str]:
        """Return the guide message to output for a poorly formatted code block in `message`."""
        content = self.codeblock_stripping(message.content, False)
        if content is None:
            return

        content, repl_code = content

        if not repl_code and not self.is_python_code(content[0]):
            return

        if content and repl_code:
            content = content[1]
        else:
            content = content[0]

        content = self.truncate(content)

        log.debug(
            f"{message.author} posted something that needed to be put inside python code "
            f"blocks. Sending the user some instructions."
        )

        content_escaped_markdown = RE_MARKDOWN.sub(r'\\\1', content)
        return (
            "It looks like you're trying to paste code into this channel.\n\n"
            "Discord has support for Markdown, which allows you to post code with full "
            "syntax highlighting. Please use these whenever you paste code, as this "
            "helps improve the legibility and makes it easier for us to help you.\n\n"
            f"**To do this, use the following method:**\n"
            f"\\`\\`\\`python\n{content_escaped_markdown}\n\\`\\`\\`\n\n"
            "**This will result in the following:**\n"
            f"```python\n{content}\n```"
        )

    @staticmethod
    def find_code_blocks(message: str) -> Sequence[CodeBlock]:
        """
        Find and return all Markdown code blocks in the `message`.

        If the `message` contains at least one code block with valid ticks and a specified language,
        return an empty sequence. This is based on the assumption that if the user managed to get
        one code block right, they already know how to fix the rest themselves.
        """
        code_blocks = []
        for _, tick, language, content in RE_CODE_BLOCK.finditer(message):
            language = language.strip()
            if tick == BACKTICK and language:
                return ()
            else:
                code_block = CodeBlock(content, language, tick)
                code_blocks.append(code_block)

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

    @staticmethod
    def has_bad_ticks(message: discord.Message) -> bool:
        """Return True if `message` starts with 3 characters which look like but aren't '`'."""
        return message.content[:3] in TICKS

    @staticmethod
    def is_help_channel(channel: discord.TextChannel) -> bool:
        """Return True if `channel` is in one of the help categories."""
        return (
            getattr(channel, "category", None)
            and channel.category.id in (Categories.help_available, Categories.help_in_use)
        )

    def is_on_cooldown(self, channel: discord.TextChannel) -> bool:
        """
        Return True if an embed was sent for `channel` in the last 300 seconds.

        Note: only channels in the `channel_cooldowns` have cooldowns enabled.
        """
        return (time.time() - self.channel_cooldowns.get(channel.id, 0)) < 300

    @staticmethod
    def is_python_code(content: str) -> bool:
        """Return True if `content` is valid Python consisting of more than just expressions."""
        try:
            # Attempt to parse the message into an AST node.
            # Invalid Python code will raise a SyntaxError.
            tree = ast.parse(content)
        except SyntaxError:
            log.trace("Code is not valid Python.")
            return False

        # Multiple lines of single words could be interpreted as expressions.
        # This check is to avoid all nodes being parsed as expressions.
        # (e.g. words over multiple lines)
        if not all(isinstance(node, ast.Expr) for node in tree.body):
            return True
        else:
            log.trace("Code consists only of expressions.")
            return False

    def is_valid_channel(self, channel: discord.TextChannel) -> bool:
        """Return True if `channel` is a help channel, may be on cooldown, or is whitelisted."""
        return (
            self.is_help_channel(channel)
            or channel.id in self.channel_cooldowns
            or channel.id in self.channel_whitelist
        )

    async def send_guide_embed(self, message: discord.Message, description: str) -> None:
        """
        Send an embed with `description` as a guide for an improperly formatted `message`.

        The embed will be deleted automatically after 5 minutes.
        """
        embed = Embed(description=description)
        bot_message = await message.channel.send(f"Hey {message.author.mention}!", embed=embed)
        self.codeblock_message_ids[message.id] = bot_message.id

        self.bot.loop.create_task(
            wait_for_deletion(bot_message, user_ids=(message.author.id,), client=self.bot)
        )

    def should_parse(self, message: discord.Message) -> bool:
        """
        Return True if `message` should be parsed.

        A qualifying message:

        1. Is not authored by a bot
        2. Is in a valid channel
        3. Has more than 3 lines
        4. Has no bot token
        """
        return (
            not message.author.bot
            and self.is_valid_channel(message.channel)
            and len(message.content.split("\n", 3)) > 3
            and not TokenRemover.find_token_in_message(message)
        )

    @staticmethod
    def truncate(content: str, max_chars: int = 204, max_lines: int = 10) -> str:
        """Return `content` truncated to be at most `max_chars` or `max_lines` in length."""
        current_length = 0
        lines_walked = 0

        for line in content.splitlines(keepends=True):
            if current_length + len(line) > max_chars or lines_walked == max_lines:
                break
            current_length += len(line)
            lines_walked += 1

        return content[:current_length] + "#..."

    @Cog.listener()
    async def on_message(self, msg: Message) -> None:
        """
        Detect poorly formatted Python code in new messages.

        If poorly formatted code is detected, send the user a helpful message explaining how to do
        properly formatted Python syntax highlighting codeblocks.
        """
        if not self.should_parse(msg):
            return

        # When debugging, ignore cooldowns.
        if self.is_on_cooldown(msg.channel) and not DEBUG_MODE:
            return

        try:
            if self.has_bad_ticks(msg):
                description = self.format_bad_ticks_message(msg)
            else:
                description = self.format_guide_message(msg)
        except SyntaxError:
            log.trace(
                f"SyntaxError while parsing code block sent by {msg.author}; "
                f"code posted probably just wasn't Python:\n\n{msg.content}\n\n"
            )
            return

        if description:
            await self.send_guide_embed(msg, description)
            if msg.channel.id not in self.channel_whitelist:
                self.channel_cooldowns[msg.channel.id] = time.time()

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
