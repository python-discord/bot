"""
Cog that prints out snippets to Discord

Matches each message against a regex and prints the contents
of the first matched snippet url
"""

import os
import re
import textwrap

from discord import Message
from discord.ext.commands import Cog
import aiohttp

from bot.bot import Bot


async def fetch_http(session: aiohttp.ClientSession, url: str, response_format='text', **kwargs) -> str:
    """Uses aiohttp to make http GET requests"""

    async with session.get(url, **kwargs) as response:
        if response_format == 'text':
            return await response.text()
        elif response_format == 'json':
            return await response.json()


async def revert_to_orig(d: dict) -> dict:
    """Replace URL Encoded values back to their original"""

    for obj in d:
        if d[obj] is not None:
            d[obj] = d[obj].replace('%2F', '/').replace('%2E', '.')


async def orig_to_encode(d: dict) -> dict:
    """Encode URL Parameters"""

    for obj in d:
        if d[obj] is not None:
            d[obj] = d[obj].replace('/', '%2F').replace('.', '%2E')


async def snippet_to_embed(d: dict, file_contents: str) -> str:
    """
    Given a regex groupdict and file contents, creates a code block
    """

    if d['end_line']:
        start_line = int(d['start_line'])
        end_line = int(d['end_line'])
    else:
        start_line = end_line = int(d['start_line'])

    split_file_contents = file_contents.split('\n')

    if start_line > end_line:
        start_line, end_line = end_line, start_line
    if start_line > len(split_file_contents) or end_line < 1:
        return ''
    start_line = max(1, start_line)
    end_line = min(len(split_file_contents), end_line)

    required = '\n'.join(split_file_contents[start_line - 1:end_line])
    required = textwrap.dedent(required).rstrip().replace('`', '`\u200b')

    language = d['file_path'].split('/')[-1].split('.')[-1]
    if not language.replace('-', '').replace('+', '').replace('_', '').isalnum():
        language = ''

    if len(required) != 0:
        return f'```{language}\n{required}```\n'
    return '``` ```\n'


GITHUB_RE = re.compile(
    r'https://github\.com/(?P<repo>.+?)/blob/(?P<branch>.+?)/'
    + r'(?P<file_path>.+?)#L(?P<start_line>\d+)([-~]L(?P<end_line>\d+))?\b'
)

GITHUB_GIST_RE = re.compile(
    r'https://gist\.github\.com/([^/]*)/(?P<gist_id>[0-9a-zA-Z]+)/*'
    + r'(?P<revision>[0-9a-zA-Z]*)/*#file-(?P<file_path>.+?)'
    + r'-L(?P<start_line>\d+)([-~]L(?P<end_line>\d+))?\b'
)

GITLAB_RE = re.compile(
    r'https://gitlab\.com/(?P<repo>.+?)/\-/blob/(?P<branch>.+?)/'
    + r'(?P<file_path>.+?)#L(?P<start_line>\d+)([-~](?P<end_line>\d+))?\b'
)

BITBUCKET_RE = re.compile(
    r'https://bitbucket\.org/(?P<repo>.+?)/src/(?P<branch>.+?)/'
    + r'(?P<file_path>.+?)#lines-(?P<start_line>\d+)(:(?P<end_line>\d+))?\b'
)


class PrintSnippets(Cog):
    def __init__(self, bot):
        """Initializes the cog's bot"""

        self.bot = bot
        self.session = aiohttp.ClientSession()

    @Cog.listener()
    async def on_message(self, message: Message) -> None:
        """
        Checks if the message starts is a GitHub snippet, then removes the embed,
        then sends the snippet in Discord
        """

        gh_match = GITHUB_RE.search(message.content)
        gh_gist_match = GITHUB_GIST_RE.search(message.content)
        gl_match = GITLAB_RE.search(message.content)
        bb_match = BITBUCKET_RE.search(message.content)

        if (gh_match or gh_gist_match or gl_match or bb_match) and not message.author.bot:
            message_to_send = ''

            for gh in GITHUB_RE.finditer(message.content):
                d = gh.groupdict()
                headers = {'Accept': 'application/vnd.github.v3.raw'}
                if 'GITHUB_TOKEN' in os.environ:
                    headers['Authorization'] = f'token {os.environ["GITHUB_TOKEN"]}'
                file_contents = await fetch_http(
                    self.session,
                    f'https://api.github.com/repos/{d["repo"]}/contents/{d["file_path"]}?ref={d["branch"]}',
                    'text',
                    headers=headers,
                )
                message_to_send += await snippet_to_embed(d, file_contents)

            for gh_gist in GITHUB_GIST_RE.finditer(message.content):
                d = gh_gist.groupdict()
                gist_json = await fetch_http(
                    self.session,
                    f'https://api.github.com/gists/{d["gist_id"]}{"/" + d["revision"] if len(d["revision"]) > 0 else ""}',
                    'json',
                )
                for f in gist_json['files']:
                    if d['file_path'] == f.lower().replace('.', '-'):
                        d['file_path'] = f
                        file_contents = await fetch_http(
                            self.session,
                            gist_json['files'][f]['raw_url'],
                            'text',
                        )
                        message_to_send += await snippet_to_embed(d, file_contents)
                        break

            for gl in GITLAB_RE.finditer(message.content):
                d = gl.groupdict()
                await orig_to_encode(d)
                headers = {}
                if 'GITLAB_TOKEN' in os.environ:
                    headers['PRIVATE-TOKEN'] = os.environ["GITLAB_TOKEN"]
                file_contents = await fetch_http(
                    self.session,
                    f'https://gitlab.com/api/v4/projects/{d["repo"]}/repository/files/{d["file_path"]}/raw?ref={d["branch"]}',
                    'text',
                    headers=headers,
                )
                await revert_to_orig(d)
                message_to_send += await snippet_to_embed(d, file_contents)

            for bb in BITBUCKET_RE.finditer(message.content):
                d = bb.groupdict()
                await orig_to_encode(d)
                file_contents = await fetch_http(
                    self.session,
                    f'https://bitbucket.org/{d["repo"]}/raw/{d["branch"]}/{d["file_path"]}',
                    'text',
                )
                await revert_to_orig(d)
                message_to_send += await snippet_to_embed(d, file_contents)

            message_to_send = message_to_send[:-1]

            if len(message_to_send) > 2000:
                await message.channel.send(
                    'Sorry, Discord has a 2000 character limit. Please send a shorter '
                    + 'snippet or split the big snippet up into several smaller ones :slight_smile:'
                )
            elif len(message_to_send) == 0:
                await message.channel.send(
                    'Please send valid snippet links to prevent spam :slight_smile:'
                )
            elif message_to_send.count('\n') > 50:
                await message.channel.send(
                    'Please limit the total number of lines to at most 50 to prevent spam :slight_smile:'
                )
            else:
                await message.channel.send(message_to_send)
            await message.edit(suppress=True)


def setup(bot: Bot) -> None:
    """Load the Utils cog."""
    bot.add_cog(PrintSnippets(bot))
