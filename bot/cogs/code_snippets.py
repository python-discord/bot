import re
import textwrap
from urllib.parse import quote_plus

from aiohttp import ClientSession
from discord import Message
from discord.ext.commands import Cog

from bot.bot import Bot
from bot.utils.messages import wait_for_deletion


async def fetch_http(session: ClientSession, url: str, response_format: str, **kwargs) -> str:
    """Uses aiohttp to make http GET requests."""
    async with session.get(url, **kwargs) as response:
        if response_format == 'text':
            return await response.text()
        elif response_format == 'json':
            return await response.json()


async def fetch_github_snippet(session: ClientSession, repo: str,
                               path: str, start_line: str, end_line: str) -> str:
    """Fetches a snippet from a GitHub repo."""
    headers = {'Accept': 'application/vnd.github.v3.raw'}

    # Search the GitHub API for the specified branch
    refs = (await fetch_http(session, f'https://api.github.com/repos/{repo}/branches', 'json', headers=headers)
            + await fetch_http(session, f'https://api.github.com/repos/{repo}/tags', 'json', headers=headers))

    ref = path.split('/')[0]
    file_path = '/'.join(path.split('/')[1:])
    for possible_ref in refs:
        if path.startswith(possible_ref['name'] + '/'):
            ref = possible_ref['name']
            file_path = path[len(ref) + 1:]
            break

    file_contents = await fetch_http(
        session,
        f'https://api.github.com/repos/{repo}/contents/{file_path}?ref={ref}',
        'text',
        headers=headers,
    )

    return await snippet_to_md(file_contents, file_path, start_line, end_line)


async def fetch_github_gist_snippet(session: ClientSession, gist_id: str, revision: str,
                                    file_path: str, start_line: str, end_line: str) -> str:
    """Fetches a snippet from a GitHub gist."""
    headers = {'Accept': 'application/vnd.github.v3.raw'}

    gist_json = await fetch_http(
        session,
        f'https://api.github.com/gists/{gist_id}{f"/{revision}" if len(revision) > 0 else ""}',
        'json',
        headers=headers,
    )

    # Check each file in the gist for the specified file
    for gist_file in gist_json['files']:
        if file_path == gist_file.lower().replace('.', '-'):
            file_contents = await fetch_http(
                session,
                gist_json['files'][gist_file]['raw_url'],
                'text',
            )

            return await snippet_to_md(file_contents, gist_file, start_line, end_line)

    return ''


async def fetch_gitlab_snippet(session: ClientSession, repo: str,
                               path: str, start_line: str, end_line: str) -> str:
    """Fetches a snippet from a GitLab repo."""
    enc_repo = quote_plus(repo)

    # Searches the GitLab API for the specified branch
    refs = (await fetch_http(session, f'https://gitlab.com/api/v4/projects/{enc_repo}/repository/branches', 'json')
            + await fetch_http(session, f'https://gitlab.com/api/v4/projects/{enc_repo}/repository/tags', 'json'))

    ref = path.split('/')[0]
    file_path = '/'.join(path.split('/')[1:])
    for possible_ref in refs:
        if path.startswith(possible_ref['name'] + '/'):
            ref = possible_ref['name']
            file_path = path[len(ref) + 1:]
            break

    enc_ref = quote_plus(ref)
    enc_file_path = quote_plus(file_path)

    file_contents = await fetch_http(
        session,
        f'https://gitlab.com/api/v4/projects/{enc_repo}/repository/files/{enc_file_path}/raw?ref={enc_ref}',
        'text',
    )

    return await snippet_to_md(file_contents, file_path, start_line, end_line)


async def fetch_bitbucket_snippet(session: ClientSession, repo: str, ref: str,
                                  file_path: str, start_line: int, end_line: int) -> str:
    """Fetches a snippet from a BitBucket repo."""
    file_contents = await fetch_http(
        session,
        f'https://bitbucket.org/{quote_plus(repo)}/raw/{quote_plus(ref)}/{quote_plus(file_path)}',
        'text',
    )

    return await snippet_to_md(file_contents, file_path, start_line, end_line)


async def snippet_to_md(file_contents: str, file_path: str, start_line: str, end_line: str) -> str:
    """Given file contents, file path, start line and end line creates a code block."""
    # Parse start_line and end_line into integers
    if end_line is None:
        start_line = end_line = int(start_line)
    else:
        start_line = int(start_line)
        end_line = int(end_line)

    split_file_contents = file_contents.splitlines()

    # Make sure that the specified lines are in range
    if start_line > end_line:
        start_line, end_line = end_line, start_line
    if start_line > len(split_file_contents) or end_line < 1:
        return ''
    start_line = max(1, start_line)
    end_line = min(len(split_file_contents), end_line)

    # Gets the code lines, dedents them, and inserts zero-width spaces to prevent Markdown injection
    required = '\n'.join(split_file_contents[start_line - 1:end_line])
    required = textwrap.dedent(required).rstrip().replace('`', '`\u200b')

    # Extracts the code language and checks whether it's a "valid" language
    language = file_path.split('/')[-1].split('.')[-1]
    if not language.replace('-', '').replace('+', '').replace('_', '').isalnum():
        language = ''

    if len(required) != 0:
        return f'```{language}\n{required}```\n'
    return ''


GITHUB_RE = re.compile(
    r'https://github\.com/(?P<repo>.+?)/blob/(?P<path>.+/.+)'
    r'#L(?P<start_line>\d+)([-~]L(?P<end_line>\d+))?\b'
)

GITHUB_GIST_RE = re.compile(
    r'https://gist\.github\.com/([^/]+)/(?P<gist_id>[^\W_]+)/*'
    r'(?P<revision>[^\W_]*)/*#file-(?P<file_path>.+?)'
    r'-L(?P<start_line>\d+)([-~]L(?P<end_line>\d+))?\b'
)

GITLAB_RE = re.compile(
    r'https://gitlab\.com/(?P<repo>.+?)/\-/blob/(?P<path>.+/.+)'
    r'#L(?P<start_line>\d+)([-](?P<end_line>\d+))?\b'
)

BITBUCKET_RE = re.compile(
    r'https://bitbucket\.org/(?P<repo>.+?)/src/(?P<ref>.+?)/'
    r'(?P<file_path>.+?)#lines-(?P<start_line>\d+)(:(?P<end_line>\d+))?\b'
)


class CodeSnippets(Cog):
    """
    Cog that prints out snippets to Discord.

    Matches each message against a regex and prints the contents of all matched snippets.
    """

    def __init__(self, bot: Bot):
        """Initializes the cog's bot."""
        self.bot = bot

    @Cog.listener()
    async def on_message(self, message: Message) -> None:
        """Checks if the message has a snippet link, removes the embed, then sends the snippet contents."""
        gh_match = GITHUB_RE.search(message.content)
        gh_gist_match = GITHUB_GIST_RE.search(message.content)
        gl_match = GITLAB_RE.search(message.content)
        bb_match = BITBUCKET_RE.search(message.content)

        if (gh_match or gh_gist_match or gl_match or bb_match) and not message.author.bot:
            message_to_send = ''

            for gh in GITHUB_RE.finditer(message.content):
                message_to_send += await fetch_github_snippet(self.bot.http_session, **gh.groupdict())

            for gh_gist in GITHUB_GIST_RE.finditer(message.content):
                message_to_send += await fetch_github_gist_snippet(self.bot.http_session, **gh_gist.groupdict())

            for gl in GITLAB_RE.finditer(message.content):
                message_to_send += await fetch_gitlab_snippet(self.bot.http_session, **gl.groupdict())

            for bb in BITBUCKET_RE.finditer(message.content):
                message_to_send += await fetch_bitbucket_snippet(self.bot.http_session, **bb.groupdict())

            if 0 < len(message_to_send) <= 2000 and message_to_send.count('\n') <= 15:
                await message.edit(suppress=True)
                await wait_for_deletion(
                    await message.channel.send(message_to_send),
                    (message.author.id,),
                    client=self.bot
                )


def setup(bot: Bot) -> None:
    """Load the CodeSnippets cog."""
    bot.add_cog(CodeSnippets(bot))
