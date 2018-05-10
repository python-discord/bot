import asyncio
import logging
import random
import string

from discord import Colour, Embed, Member, Reaction
from discord.ext.commands import AutoShardedBot, Context, command

from bot.constants import SITE_API_KEY, SITE_API_SNAKE_QUIZ_URL

log = logging.getLogger(__name__)

# Antidote constants
SYRINGE_EMOJI = "\U0001F489"  # :syringe:
PILL_EMOJI = "\U0001F48A"     # :pill:
HOURGLASS_EMOJI = "\u231B"    # :hourglass:
CROSSBONES_EMOJI = "\u2620"   # :skull_crossbones:
ALEMBIC_EMOJI = "\u2697"      # :alembic:
TICK_EMOJI = "\u2705"         # :white_check_mark: - Correct peg, correct hole
CROSS_EMOJI = "\u274C"        # :x: - Wrong peg, wrong hole
BLANK_EMOJI = "\u26AA"        # :white_circle: - Correct peg, wrong hole
HOLE_EMOJI = "\u2B1C"         # :white_square: - Used in guesses
EMPTY_UNICODE = "\u200b"      # literally just an empty space

ANTIDOTE_EMOJI = [
    SYRINGE_EMOJI,
    PILL_EMOJI,
    HOURGLASS_EMOJI,
    CROSSBONES_EMOJI,
    ALEMBIC_EMOJI,
]

# Quiz constants
ANSWERS_EMOJI = {
    "a": "\U0001F1E6",  # :regional_indicator_a: 🇦
    "b": "\U0001F1E7",  # :regional_indicator_b: 🇧
    "c": "\U0001F1E8",  # :regional_indicator_c: 🇨
    "d": "\U0001F1E9",  # :regional_indicator_d: 🇩
}


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
        self.headers = {"X-API-KEY": SITE_API_KEY}

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

    @command(name="snakes.antidote()", alias=["snakes.antidote"])
    async def antidote(self, ctx: Context):
        """
        Antidote - Can you create the antivenom before the patient dies?

        Rules:  You have 4 ingredients for each antidote, you only have 10 attempts
                Once you synthesize the antidote, you will be presented with 4 markers
                Tick: This means you have a CORRECT ingredient in the CORRECT position
                Circle: This means you have a CORRECT ingredient in the WRONG position
                Cross: This means you have a WRONG ingredient in the WRONG position

        Info:   The game automatically ends after 5 minutes inactivity.
                You should only use each ingredient once.

        This game was created by Bisk and Runew0lf for the first PythonDiscord codejam.
        """

        # Check to see if the bot can remove reactions
        if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            await ctx.send("Unable to start game as I dont have manage_messages permissions")
            return

        # Initialize variables
        antidote_tries = 0
        antidote_guess_count = 0
        antidote_guess_list = []
        guess_result = []
        board = []
        page_guess_list = []
        page_result_list = []
        win = False

        antidote_embed = Embed(color=ctx.me.color, title="Antidote")
        antidote_embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)

        # Generate answer
        antidote_answer = list(ANTIDOTE_EMOJI)  # Duplicate list, not reference it
        random.shuffle(antidote_answer)
        antidote_answer.pop()
        log.info(antidote_answer)

        # Begin initial board building
        for i in range(0, 10):
            page_guess_list.append(f"{HOLE_EMOJI} {HOLE_EMOJI} {HOLE_EMOJI} {HOLE_EMOJI}")
            page_result_list.append(f"{CROSS_EMOJI} {CROSS_EMOJI} {CROSS_EMOJI} {CROSS_EMOJI}")
            board.append(f"`{i+1:02d}` "
                         f"{page_guess_list[i]} - "
                         f"{page_result_list[i]}")
            board.append(EMPTY_UNICODE)
        antidote_embed.add_field(name="10 guesses remaining", value="\n".join(board))
        board_id = await ctx.send(embed=antidote_embed)  # Display board

        # Add our player reactions
        for emoji in ANTIDOTE_EMOJI:
            await board_id.add_reaction(emoji)

        def event_check(reaction_: Reaction, user_: Member):
            """
            Make sure that this reaction is what we want to operate on
            """
            return (
                # Conditions for a successful pagination:
                all((
                    reaction_.message.id == board_id.id,  # Reaction is on this message
                    reaction_.emoji in ANTIDOTE_EMOJI,  # Reaction is one of the pagination emotes
                    user_.id != self.bot.user.id,  # Reaction was not made by the Bot
                    user_.id == ctx.author.id  # There were no restrictions
                ))
            )

        # Begin main game loop
        while not win and antidote_tries < 10:
            try:
                reaction, user = await ctx.bot.wait_for("reaction_add", timeout=300, check=event_check)
            except asyncio.TimeoutError:
                log.debug("Timed out waiting for a reaction")
                break  # We're done, no reactions for the last 5 minutes

            if antidote_tries < 10:
                if antidote_guess_count < 4:
                    if reaction.emoji in ANTIDOTE_EMOJI:
                        antidote_guess_list.append(reaction.emoji)
                        antidote_guess_count += 1

                    if antidote_guess_count == 4:  # Guesses complete
                        antidote_guess_count = 0
                        page_guess_list[antidote_tries] = " ".join(antidote_guess_list)
                        log.info(f"Guess: {' '.join(antidote_guess_list)}")

                        # Now check guess
                        for i in range(0, len(antidote_answer)):
                            if antidote_guess_list[i] == antidote_answer[i]:
                                guess_result.append(TICK_EMOJI)
                            elif antidote_guess_list[i] in antidote_answer:
                                guess_result.append(BLANK_EMOJI)
                            else:
                                guess_result.append(CROSS_EMOJI)
                        guess_result.sort()
                        page_result_list[antidote_tries] = " ".join(guess_result)
                        log.info(f"Guess Result: {' '.join(guess_result)}")

                        # Rebuild the board
                        board = []
                        for i in range(0, 10):
                            board.append(f"`{i+1:02d}` "
                                         f"{page_guess_list[i]} - "
                                         f"{page_result_list[i]}")
                            board.append(EMPTY_UNICODE)

                        # Remove Reactions
                        for emoji in antidote_guess_list:
                            await board_id.remove_reaction(emoji, user)

                        if antidote_guess_list == antidote_answer:
                            win = True

                        antidote_tries += 1
                        guess_result = []
                        antidote_guess_list = []

                        antidote_embed.clear_fields()
                        antidote_embed.add_field(name=f"{10 - antidote_tries} "
                                                      f"guesses remaining",
                                                 value="\n".join(board))
                        # Redisplay the board
                        await board_id.edit(embed=antidote_embed)

        # Winning / Ending Screen
        if win is True:
            antidote_embed = Embed(color=ctx.me.color, title="Antidote")
            antidote_embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
            antidote_embed.set_image(url="https://i.makeagif.com/media/7-12-2015/Cj1pts.gif")
            antidote_embed.add_field(name=f"You have created the snake antidote!",
                                     value=f"The solution was: {' '.join(antidote_answer)}\n"
                                           f"You had {10 - antidote_tries} tries remaining.")
            await board_id.edit(embed=antidote_embed)
        else:
            antidote_embed = Embed(color=ctx.me.color, title="Antidote")
            antidote_embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
            antidote_embed.set_image(url="https://media.giphy.com/media/ceeN6U57leAhi/giphy.gif")
            antidote_embed.add_field(name=EMPTY_UNICODE,
                                     value=f"Sorry you didnt make the antidote in time.\n"
                                           f"The formula was {' '.join(antidote_answer)}")
            await board_id.edit(embed=antidote_embed)

        log.debug("Ending pagination and removing all reactions...")
        await board_id.clear_reactions()

    @command(name="snakes.quiz()", alias=["snakes.quiz"])
    async def quiz(self, ctx: Context):
        """
        Asks a snake-related question in the chat and validates the user's guess.
        """

        def valid_answer(reaction, user):
            """
            Test if the the answer is valid and can be evaluated.
            """
            return (
                reaction.message.id == quiz.id                     # The reaction is attached to the question we asked.
                and user == ctx.author                             # It's the user who triggered the quiz.
                and str(reaction.emoji) in ANSWERS_EMOJI.values()  # The reaction is one of the options.
            )

        # Prepare a question.
        response = await self.bot.http_session.get(SITE_API_SNAKE_QUIZ_URL, headers=self.headers)
        question = await response.json()
        answer = question["answerkey"]
        options = {key: question[key] for key in ANSWERS_EMOJI.keys()}

        # Build and send the embed.
        embed = Embed(
            title=question["question"],
            description="\n".join(
                [f"**{key.upper()}**: {answer}" for key, answer in options.items()]
            )
        )
        quiz = await ctx.channel.send("", embed=embed)
        for emoji in ANSWERS_EMOJI.values():
            await quiz.add_reaction(emoji)

        # Validate the answer
        try:
            reaction, user = await ctx.bot.wait_for("reaction_add", timeout=20.0, check=valid_answer)
        except asyncio.TimeoutError:
            await ctx.channel.send("Bah! You took too long.")
            return

        if str(reaction.emoji) == ANSWERS_EMOJI[answer]:
            await ctx.channel.send("You got it! Well done!")
        else:
            await ctx.channel.send(
                f"Sorry, that's incorrect. The correct answer was **{answer}**."
            )


def setup(bot):
    bot.add_cog(Snakes(bot))
    log.info("Cog loaded: Snakes")
