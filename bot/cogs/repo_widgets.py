"""
Cog that sends pretty embeds of repos

Matches each message against a regex and prints the contents
of the first matched snippet url
"""

import os
import re

from discord import Embed, Message
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


async def orig_to_encode(d: dict) -> dict:
    """Encode URL Parameters"""

    for obj in d:
        if d[obj] is not None:
            d[obj] = d[obj].replace('/', '%2F').replace('.', '%2E')


GITHUB_RE = re.compile(
    r'https://github\.com/(?P<owner>[^/]+?)/(?P<repo>[^/]+?)(?:\s|$)')

GITLAB_RE = re.compile(
    r'https://gitlab\.com/(?P<owner>[^/]+?)/(?P<repo>[^/]+?)(?:\s|$)')


class RepoWidgets(Cog):
    def __init__(self, bot: Bot):
        """Initializes the cog's bot"""

        self.bot = bot
        self.session = aiohttp.ClientSession()

    @Cog.listener()
    async def on_message(self, message: Message) -> None:
        """
        Checks if the message starts is a GitHub repo link, then removes the embed,
        then sends a rich embed to Discord
        """

        gh_match = GITHUB_RE.search(message.content)
        gl_match = GITLAB_RE.search(message.content)

        if (gh_match or gl_match) and not message.author.bot:
            for gh in GITHUB_RE.finditer(message.content):
                d = gh.groupdict()
                headers = {}
                if 'GITHUB_TOKEN' in os.environ:
                    headers['Authorization'] = f'token {os.environ["GITHUB_TOKEN"]}'
                repo = await fetch_http(
                    self.session,
                    f'https://api.github.com/repos/{d["owner"]}/{d["repo"]}',
                    'json',
                    headers=headers,
                )

                embed = Embed(
                    title=repo['full_name'],
                    description='No description provided' if repo[
                        'description'] is None else repo['description'],
                    url=repo['html_url'],
                    color=0x111111
                ).set_footer(
                    text=f'Language: {repo["language"]} | ' +
                         f'Stars: {repo["stargazers_count"]} | ' +
                         f'Forks: {repo["forks_count"]} | ' +
                         f'Size: {repo["size"]}kb'
                ).set_thumbnail(url=repo['owner']['avatar_url'])
                if repo['homepage']:
                    embed.add_field(name='Website', value=repo['homepage'])
                await message.channel.send(embed=embed)

            for gl in GITLAB_RE.finditer(message.content):
                d = gl.groupdict()
                await orig_to_encode(d)
                headers = {}
                if 'GITLAB_TOKEN' in os.environ:
                    headers['PRIVATE-TOKEN'] = os.environ["GITLAB_TOKEN"]
                repo = await fetch_http(
                    self.session,
                    f'https://gitlab.com/api/v4/projects/{d["owner"]}%2F{d["repo"]}',
                    'json',
                    headers=headers,
                )

                embed = Embed(
                    title=repo['path_with_namespace'],
                    description='No description provided' if repo[
                        'description'] == "" else repo['description'],
                    url=repo['web_url'],
                    color=0x111111
                ).set_footer(
                    text=f'Stars: {repo["star_count"]} | ' +
                         f'Forks: {repo["forks_count"]}'
                )

                if repo['avatar_url'] is not None:
                    embed.set_thumbnail(url=repo['avatar_url'])

                await message.channel.send(embed=embed)

            await message.edit(suppress=True)


def setup(bot: Bot) -> None:
    """Load the Utils cog."""
    bot.add_cog(RepoWidgets(bot))
