import asyncio
import logging
import random
import string
import urllib

from discord import Embed, File, Member, Reaction
from discord.ext.commands import AutoShardedBot, Context, command, group

from bot.constants import SITE_API_KEY, SITE_API_URL, YOUTUBE_API_KEY
from bot.utils.snakes import hatching, perlin, perlinsneks, sal

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

ANSWERS_EMOJI_REVERSE = {
    "\U0001F1E6": "A",  # :regional_indicator_a: 🇦
    "\U0001F1E7": "B",  # :regional_indicator_b: 🇧
    "\U0001F1E8": "C",  # :regional_indicator_c: 🇨
    "\U0001F1E9": "D",  # :regional_indicator_d: 🇩
}

# Zzzen of pythhhon constant
ZEN = """
Beautiful is better than ugly.
Explicit is better than implicit.
Simple is better than complex.
Complex is better than complicated.
Flat is better than nested.
Sparse is better than dense.
Readability counts.
Special cases aren't special enough to break the rules.
Although practicality beats purity.
Errors should never pass silently.
Unless explicitly silenced.
In the face of ambiguity, refuse the temptation to guess.
There should be one-- and preferably only one --obvious way to do it.
Now is better than never.
Although never is often better than *right* now.
If the implementation is hard to explain, it's a bad idea.
If the implementation is easy to explain, it may be a good idea.
"""

# Max messages to train snake_chat on
MSG_MAX = 100

# Rattlesnake mp3s
RATTLES = [
    'rattle1.mp3',
    'rattle2.mp3',
    'rattle3.mp3',
    'rattle4.mp3'
]


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
        self.quiz_url = f"{SITE_API_URL}/snake_quiz"
        self.fact_url = f"{SITE_API_URL}/snake_fact"

    @staticmethod
    def _snakify(message):
        """
        Sssnakifffiesss a sstring.
        """

        # Replace fricatives with exaggerated snake fricatives.
        simple_fricatives = [
            "f", "s", "z", "h",
            "F", "S", "Z", "H",
        ]
        complex_fricatives = [
            "th", "sh", "Th", "Sh"
        ]

        for letter in simple_fricatives:
            if letter.islower():
                message = message.replace(letter, letter * random.randint(2, 4))
            else:
                message = message.replace(letter, (letter * random.randint(2, 4)).title())

        for fricative in complex_fricatives:
            message = message.replace(fricative, fricative[0] + fricative[1] * random.randint(2, 4))

        return message

    def get_snake_name(self) -> str:
        """
        Gets a random snake name.
        :return: A random snake name, as a string.
        """
        return random.choice(self.SNAKES)

    @command(name="snakes.name()", aliases=["snakes.name", "snakes.name_gen", "snakes.name_gen()"])
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
            title="Snake name",
            description=f"Your snake-name is **{result}**",
            color=0x399600
        )

        return await ctx.send(embed=embed)

    @command(name="snakes.antidote()", aliases=["snakes.antidote"])
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
            log.warning(f"Unable to start Antidote game - Missing manage_messages permissions in {ctx.channel}")
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

        antidote_embed = Embed(color=0x399600, title="Antidote")
        antidote_embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)

        # Generate answer
        antidote_answer = list(ANTIDOTE_EMOJI)  # Duplicate list, not reference it
        random.shuffle(antidote_answer)
        antidote_answer.pop()

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
                log.debug("Antidote timed out waiting for a reaction")
                break  # We're done, no reactions for the last 5 minutes

            if antidote_tries < 10:
                if antidote_guess_count < 4:
                    if reaction.emoji in ANTIDOTE_EMOJI:
                        antidote_guess_list.append(reaction.emoji)
                        antidote_guess_count += 1

                    if antidote_guess_count == 4:  # Guesses complete
                        antidote_guess_count = 0
                        page_guess_list[antidote_tries] = " ".join(antidote_guess_list)

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
            antidote_embed = Embed(color=0x399600, title="Antidote")
            antidote_embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
            antidote_embed.set_image(url="https://i.makeagif.com/media/7-12-2015/Cj1pts.gif")
            antidote_embed.add_field(name=f"You have created the snake antidote!",
                                     value=f"The solution was: {' '.join(antidote_answer)}\n"
                                           f"You had {10 - antidote_tries} tries remaining.")
            await board_id.edit(embed=antidote_embed)
        else:
            antidote_embed = Embed(color=0x399600, title="Antidote")
            antidote_embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
            antidote_embed.set_image(url="https://media.giphy.com/media/ceeN6U57leAhi/giphy.gif")
            antidote_embed.add_field(name=EMPTY_UNICODE,
                                     value=f"Sorry you didnt make the antidote in time.\n"
                                           f"The formula was {' '.join(antidote_answer)}")
            await board_id.edit(embed=antidote_embed)

        log.debug("Ending pagination and removing all reactions...")
        await board_id.clear_reactions()

    @command(name="snakes.quiz()", aliases=["snakes.quiz"])
    async def quiz(self, ctx: Context):
        """
        Asks a snake-related question in the chat and validates the user's guess.

        This was created by Mushy and Cardium for the code jam,
        and modified by lemon for inclusion in this bot.
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
        response = await self.bot.http_session.get(self.quiz_url, headers=self.headers)
        question = await response.json()
        answer = question["answerkey"]
        options = {key: question[key] for key in ANSWERS_EMOJI.keys()}

        # Build and send the embed.
        embed = Embed(
            color=0x399600,
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
            await ctx.channel.send(f"You selected **{options[answer]}**, which is correct! Well done!")
        else:
            wrong_answer = ANSWERS_EMOJI_REVERSE[str(reaction.emoji)]
            await ctx.channel.send(
                f"Sorry, **{wrong_answer}** is incorrect. The correct answer was \"**{options[answer]}**\"."
            )

    @command(name="snakes.zen()", aliases=["zen"])
    async def zen(self, ctx: Context):
        """
        Gets a random quote from the Zen of Python.

        Written by Prithaj and Andrew during the very first code jam.
        Modified by lemon for inclusion in the bot.
        """

        embed = Embed(
            title="Zzzen of Pythhon",
            color=0x399600
        )

        # Get the zen quote and snakify it
        zen_quote = random.choice(ZEN.splitlines())
        zen_quote = self._snakify(zen_quote)

        # Embed and send
        embed.description = zen_quote
        await ctx.channel.send(
            embed=embed
        )

    @command(name="snakes.snakify()", aliases=["snakes.snakify"])
    async def snake_chat(self, ctx: Context, message: str = None):
        """
        How would I talk if I were a snake?
        :param ctx: context
        :param message: If this is passed, it will snakify the message.
                        If not, it will snakify a random message from
                        the users history.
        """

        def predicate(message):
            """
            Check if the message was sent by the author.
            """
            return message.author == ctx.message.author

        def get_random_long_message(messages, retries=10):
            """
            Fetch a message that's at least 3 words long,
            but only if it is possible to do so in retries
            attempts. Else, just return whatever the last
            message is.
            """
            long_message = random.choice(messages)
            if len(long_message.split()) < 3 or retries <= 0:
                return get_random_long_message(messages, retries - 1)
            return long_message

        embed = Embed()
        user = ctx.message.author

        if not message:

            # Get a random message from the users history
            messages = []
            async for message in ctx.channel.history(limit=500).filter(predicate):
                messages.append(message.content)

            message = get_random_long_message(messages)

        # Set the avatar
        if user.avatar is not None:
            avatar = f"https://cdn.discordapp.com/avatars/{user.id}/{user.avatar}"
        else:
            avatar = (
                "https://img00.deviantart.net/eee3/i/2017/168/3/4/"
                "discord__app__avatar_rev1_by_nodeviantarthere-dbd2tp9.png"
            )

        # Build and send the embed
        embed.set_author(
            name=f"{user.name}#{user.discriminator}",
            icon_url=avatar,
        )
        embed.description = f"*{self._snakify(message)}*"

        await ctx.channel.send(embed=embed)

    @command(name="snakes.fact()", aliases=["snakes.fact"])
    async def snake_fact(self, ctx: Context):
        """
        Gets a snake-related fact

        This was created by Prithaj and Andrew for code jam 1,
        and modified by lemon for inclusion in this bot.
        """

        # Get a fact from the API.
        response = await self.bot.http_session.get(self.fact_url, headers=self.headers)
        question = await response.json()

        # Build and send the embed.
        embed = Embed(
            title="Snake fact",
            color=0x399600,
            description=question
        )
        await ctx.channel.send(embed=embed)

    @command(name="snakes.draw()", aliases=["snakes.draw"])
    async def draw(self, ctx: Context):
        """
        Draws a random snek using Perlin noise

        Made by Momo and kel during the first code jam.
        """

        # Generate random snake attributes
        width = random.randint(8, 12)
        length = random.randint(15, 22)
        snek_color, text_color = random.sample(perlinsneks.SNAKE_COLORS, 2)
        text = random.choice(perlinsneks.SNAKE_TEXTS)

        # Build and send the snek
        factory = perlin.PerlinNoiseFactory(dimension=1, octaves=2)
        image_frame = perlinsneks.create_snek_frame(
            factory,
            snake_width=width,
            snake_length=length,
            snake_color=snek_color,
            text=text,
            text_color=text_color,
        )
        png_bytes = perlinsneks.frame_to_png_bytes(image_frame)

        file = File(png_bytes, filename='snek.png')

        await ctx.send(file=file)

    @command(name="snakes.hatch()", aliases=["snakes.hatch", "hatch"])
    async def hatch(self, ctx: Context):
        """
        Hatches your personal snake

        Made by Momo and kel during the first code jam.
        """

        # Pick a random snake to hatch.
        snake_name = random.choice(list(hatching.snakes.keys()))
        snake_image = hatching.snakes[snake_name]

        # Hatch the snake
        message = await ctx.channel.send(embed=Embed(description="Hatching your snake :snake:..."))
        await asyncio.sleep(1)

        for stage in hatching.stages:
            hatch_embed = Embed(description=stage)
            await message.edit(embed=hatch_embed)
            await asyncio.sleep(1)
        await asyncio.sleep(1)
        await message.delete()

        # Build and send the embed.
        my_snake_embed = Embed(description=":tada: Congrats! You hatched: **{0}**".format(snake_name))
        my_snake_embed.set_thumbnail(url=snake_image)
        my_snake_embed.set_footer(
            text=" Owner: {0}#{1}".format(ctx.message.author.name, ctx.message.author.discriminator)
        )

        await ctx.channel.send(embed=my_snake_embed)

    @command(name="snakes.video()", aliases=["snakes.video", "snakes.get_video()", "snakes.get_video"])
    async def video(self, ctx: Context, search: str = None):
        """
        Gets a YouTube video about snakes
        :param name: Optional, a name of a snake. Used to search for videos with that name
        :param ctx: Context object passed from discord.py

        Created by Andrew and Prithaj for the first code jam.
        """

        # Are we searching for anything specific?
        if search:
            query = search + ' snake'
        else:
            query = 'snake'

        # Build the URL and make the request
        url = f'https://www.googleapis.com/youtube/v3/search'
        response = await self.bot.http_session.get(
            url,
            params={
                "part": "snippet",
                "q": urllib.parse.quote(query),
                "type": "video",
                "key": YOUTUBE_API_KEY
            }
        )
        response = await response.json()
        data = response['items']

        # Send the user a video
        num = random.randint(0, 5)  # 5 videos are returned from the api
        youtube_base_url = 'https://www.youtube.com/watch?v='
        await ctx.channel.send(
            content=f"{youtube_base_url}{data[num]['id']['videoId']}"
        )

    # region: Snakes and Ladders group
    @group(name="snakes.sal()", aliases=["snakes.sal"])
    async def sal(self, ctx: Context):
        """
        Command group for Snakes and Ladders
        - Create a S&L game: sal create
        - Join a S&L game: sal join
        - Leave a S&L game: sal leave
        - Cancel a S&L game (author): sal cancel
        - Start a S&L game (author): sal start
        - Roll the dice: sal roll OR roll
        """
        if ctx.invoked_subcommand is None:
            # alias for 'sal roll' -> roll()
            if ctx.subcommand_passed is not None and ctx.subcommand_passed.lower() == "roll":
                await self.bot.get_command("roll()").invoke(ctx)
                return
            await ctx.send("{0} Unknown S&L command".format(ctx.author.mention))

    @sal.command(name="snakes.sal.create()", aliases=["snakes.sal.create"])
    async def create_sal(self, ctx: Context):
        """
        Create a Snakes and Ladders in the channel.
        """
        # check if there is already a game in this channel
        channel = ctx.channel
        if channel in self.active_sal:
            await ctx.send("{0} A game is already in progress in this channel.".format(ctx.author.mention))
            return
        game = sal.SnakeAndLaddersGame(snakes=self, channel=channel, author=ctx.author)
        self.active_sal[channel] = game
        await game.open_game()

    @sal.command(name="join()", aliases=["join"])
    async def join_sal(self, ctx: Context):
        """
        Join a Snakes and Ladders game in the channel.
        """
        channel = ctx.channel
        if channel not in self.active_sal:
            await ctx.send(
                "{0} There is no active Snakes & Ladders game in this channel.".format(ctx.author.mention))
            return
        game = self.active_sal[channel]
        await game.player_join(ctx.author)

    @sal.command(name="leave()", aliases=["leave", "quit"])
    async def leave_sal(self, ctx: Context):
        """
        Leave the Snakes and Ladders game.
        """
        channel = ctx.channel
        if channel not in self.active_sal:
            await ctx.send(
                "{0} There is no active Snakes & Ladders game in this channel.".format(ctx.author.mention))
            return
        game = self.active_sal[channel]
        await game.player_leave(ctx.author)

    @sal.command(name="cancel()", aliases=["cancel"])
    async def cancel_sal(self, ctx: Context):
        """
        Cancel the Snakes and Ladders game (author only).
        """
        channel = ctx.channel
        if channel not in self.active_sal:
            await ctx.send(
                "{0} There is no active Snakes & Ladders game in this channel.".format(ctx.author.mention))
            return
        game = self.active_sal[channel]
        await game.cancel_game(ctx.author)

    @sal.command(name="start()", aliases=["start"])
    async def start_sal(self, ctx: Context):
        """
        Start the Snakes and Ladders game (author only).
        """
        channel = ctx.channel
        if channel not in self.active_sal:
            await ctx.send(
                "{0} There is no active Snakes & Ladders game in this channel.".format(ctx.author.mention))
            return
        game = self.active_sal[channel]
        await game.start_game(ctx.author)

    @command(name="roll()", aliases=["sal roll", "roll"])
    async def roll_sal(self, ctx: Context):
        """
        Roll the dice in Snakes and Ladders.
        """
        channel = ctx.channel
        if channel not in self.active_sal:
            await ctx.send(
                "{0} There is no active Snakes & Ladders game in this channel.".format(ctx.author.mention))
            return
        game = self.active_sal[channel]

        await game.player_roll(ctx.author)
    # endregion


def setup(bot):
    bot.add_cog(Snakes(bot))
    log.info("Cog loaded: Snakes")
