import re
import textwrap
from urllib.parse import quote_plus

from discord import Message
from discord.ext.commands import Cog

from bot.bot import Bot
from bot.utils.messages import wait_for_deletion


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
    Cog that parses and sends code snippets to Discord.

    Matches each message against a regex and prints the contents of all matched snippets.
    """

    async def _fetch_response(self, url: str, response_format: str, **kwargs) -> str:
        """Makes http requests using aiohttp."""
        async with self.bot.http_session.get(url, **kwargs) as response:
            if response_format == 'text':
                return await response.text()
            elif response_format == 'json':
                return await response.json()

    def _find_ref(self, path: str, refs: tuple) -> tuple:
        """Loops through all branches and tags to find the required ref."""
        # Base case: there is no slash in the branch name
        ref = path.split('/')[0]
        file_path = '/'.join(path.split('/')[1:])
        # In case there are slashes in the branch name, we loop through all branches and tags
        for possible_ref in refs:
            if path.startswith(possible_ref['name'] + '/'):
                ref = possible_ref['name']
                file_path = path[len(ref) + 1:]
                break
        return (ref, file_path)

    async def _fetch_github_snippet(
        self,
        repo: str,
        path: str,
        start_line: str,
        end_line: str
    ) -> str:
        """Fetches a snippet from a GitHub repo."""
        headers = {'Accept': 'application/vnd.github.v3.raw'}

        # Search the GitHub API for the specified branch
        branches = await self._fetch_response(f'https://api.github.com/repos/{repo}/branches', 'json', headers=headers)
        tags = await self._fetch_response(f'https://api.github.com/repos/{repo}/tags', 'json', headers=headers)
        refs = branches + tags
        ref, file_path = self._find_ref(path, refs)

        file_contents = await self._fetch_response(
            f'https://api.github.com/repos/{repo}/contents/{file_path}?ref={ref}',
            'text',
            headers=headers,
        )
        return self._snippet_to_codeblock(file_contents, file_path, start_line, end_line)

    async def _fetch_github_gist_snippet(
        self,
        gist_id: str,
        revision: str,
        file_path: str,
        start_line: str,
        end_line: str
    ) -> str:
        """Fetches a snippet from a GitHub gist."""
        headers = {'Accept': 'application/vnd.github.v3.raw'}

        gist_json = await self._fetch_response(
            f'https://api.github.com/gists/{gist_id}{f"/{revision}" if len(revision) > 0 else ""}',
            'json',
            headers=headers,
        )

        # Check each file in the gist for the specified file
        for gist_file in gist_json['files']:
            if file_path == gist_file.lower().replace('.', '-'):
                file_contents = await self._fetch_response(
                    gist_json['files'][gist_file]['raw_url'],
                    'text',
                )
                return self._snippet_to_codeblock(file_contents, gist_file, start_line, end_line)
        return ''

    async def _fetch_gitlab_snippet(
        self,
        repo: str,
        path: str,
        start_line: str,
        end_line: str
    ) -> str:
        """Fetches a snippet from a GitLab repo."""
        enc_repo = quote_plus(repo)

        # Searches the GitLab API for the specified branch
        branches = await self._fetch_response(f'https://api.github.com/repos/{repo}/branches', 'json')
        tags = await self._fetch_response(f'https://api.github.com/repos/{repo}/tags', 'json')
        refs = branches + tags
        ref, file_path = self._find_ref(path, refs)
        enc_ref = quote_plus(ref)
        enc_file_path = quote_plus(file_path)

        file_contents = await self._fetch_response(
            f'https://gitlab.com/api/v4/projects/{enc_repo}/repository/files/{enc_file_path}/raw?ref={enc_ref}',
            'text',
        )
        return self._snippet_to_codeblock(file_contents, file_path, start_line, end_line)

    async def _fetch_bitbucket_snippet(
        self,
        repo: str,
        ref: str,
        file_path: str,
        start_line: int,
        end_line: int
    ) -> str:
        """Fetches a snippet from a BitBucket repo."""
        file_contents = await self._fetch_response(
            f'https://bitbucket.org/{quote_plus(repo)}/raw/{quote_plus(ref)}/{quote_plus(file_path)}',
            'text',
        )
        return self._snippet_to_codeblock(file_contents, file_path, start_line, end_line)

    def _snippet_to_codeblock(self, file_contents: str, file_path: str, start_line: str, end_line: str) -> str:
        """
        Given the entire file contents and target lines, creates a code block.

        First, we split the file contents into a list of lines and then keep and join only the required
        ones together.

        We then dedent the lines to look nice, and replace all ` characters with `\u200b to prevent
        markdown injection.

        Finally, we surround the code with ``` characters.
        """
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
        trimmed_language = language.replace('-', '').replace('+', '').replace('_', '')
        is_valid_language = trimmed_language.isalnum()
        if not is_valid_language:
            language = ''

        if len(required) != 0:
            return f'```{language}\n{required}```\n'
        return ''

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
                message_to_send += await self._fetch_github_snippet(**gh.groupdict())

            for gh_gist in GITHUB_GIST_RE.finditer(message.content):
                message_to_send += await self._fetch_github_gist_snippet(**gh_gist.groupdict())

            for gl in GITLAB_RE.finditer(message.content):
                message_to_send += await self._fetch_gitlab_snippet(**gl.groupdict())

            for bb in BITBUCKET_RE.finditer(message.content):
                message_to_send += await self._fetch_bitbucket_snippet(**bb.groupdict())

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
