import logging
import random
import string

from discord import Colour, Embed
from discord.ext.commands import AutoShardedBot, Context, command

log = logging.getLogger(__name__)


class Snakes:
    """
    Commands related to snakes. These were created by our
    community during the first code jam.

    More information can be found in the code-jam-1 repo.

    https://github.com/discord-python/code-jam-1
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot
        self.SNAKES = ['black cobra', 'children\'s python']  # temporary

    def get_snake_name(self) -> str:
        """
        Gets a random snake name.
        :return: A random snake name, as a string.
        """
        return random.choice(self.SNAKES)

    @command(name="snakes.name_gen()", aliases=["snakes.name_gen"])
    async def random_snake_name(self, ctx: Context, name: str = None):
        """
        Slices the users name at the last vowel (or second last if the name
        ends with a vowel), and then combines it with a random snake name,
        which is sliced at the first vowel (or second if the name starts with
        a vowel).

        If the name contains no vowels, it just appends the snakename
        to the end of the name.

        Examples:
            lemon + anaconda = lemoconda
            krzsn + anaconda = krzsnconda
            gdude + anaconda = gduconda
            aperture + anaconda = apertuconda
            lucy + python = luthon
            joseph + taipan = joseipan

        This was written by Iceman, and modified for inclusion into the bot by lemon.
        """

        snake_name = self.get_snake_name()
        snake_prefix = ""

        # Set aside every word in the snake name except the last.
        if " " in snake_name:
            snake_prefix = " ".join(snake_name.split()[:-1])
            snake_name = snake_name.split()[-1]

        # If no name is provided, use whoever called the command.
        if name:
            user_name = name
        else:
            user_name = ctx.author.display_name

        # Get the index of the vowel to slice the username at
        user_slice_index = len(user_name)
        for index, char in enumerate(reversed(user_name)):
            if index == 0:
                continue
            if char.lower() in "aeiouy":
                user_slice_index -= index
                break
        log.trace(f"name is {user_name}, index is {user_slice_index}")

        # Now, get the index of the vowel to slice the snake_name at
        snake_slice_index = 0
        for index, char in enumerate(snake_name):
            if index == 0:
                continue
            if char.lower() in "aeiouy":
                snake_slice_index = index + 1
                break
        log.trace(f"snake name is {snake_name}, index is {snake_slice_index}")

        # Combine!
        snake_name = snake_name[snake_slice_index:]
        user_name = user_name[:user_slice_index]
        result = f"{snake_prefix} {user_name}{snake_name}"
        result = string.capwords(result)

        # Embed and send
        embed = Embed(
            description=f"Your snake-name is **{result}**",
            color=Colour.blurple()
        )

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Snakes(bot))
    log.info("Cog loaded: Snakes")
