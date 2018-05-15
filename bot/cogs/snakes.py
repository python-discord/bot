import asyncio
import colorsys
import logging
import random
import re
import string
import urllib
from typing import Any, Dict

import aiohttp
import async_timeout
from discord import Embed, File, Member, Reaction
from discord.ext.commands import AutoShardedBot, Context, bot_has_permissions, command

from bot.constants import OMDB_API_KEY, SITE_API_KEY, SITE_API_URL, YOUTUBE_API_KEY
from bot.converters import Snake
from bot.decorators import locked
from bot.utils.snakes import hatching, perlin, perlinsneks, sal

log = logging.getLogger(__name__)

# Color
SNAKE_COLOR = 0x399600

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

# get_snek constants
URL = "https://en.wikipedia.org/w/api.php?"


class Snakes:
    """
    Commands related to snakes. These were created by our
    community during the first code jam.

    More information can be found in the code-jam-1 repo.

    https://github.com/discord-python/code-jam-1
    """

    wiki_brief = re.compile(r'(.*?)(=+ (.*?) =+)', flags=re.DOTALL)
    valid = ('gif', 'png', 'jpeg', 'jpg', 'webp')

    def __init__(self, bot: AutoShardedBot):
        self.active_sal = {}
        self.bot = bot
        self.headers = {"X-API-KEY": SITE_API_KEY}

        # Build API urls.
        self.quiz_url = f"{SITE_API_URL}/snake_quiz"
        self.facts_url = f"{SITE_API_URL}/snake_facts"
        self.names_url = f"{SITE_API_URL}/snake_names"
        self.idioms_url = f"{SITE_API_URL}/snake_idioms"

    async def _fetch(self, session, url, params=None):
        if params is None:
            params = {}

        async with async_timeout.timeout(10):
            async with session.get(url, params=params) as response:
                return await response.json()

    async def get_snek(self, name: str) -> Dict[str, Any]:
        """
        Goes online and fetches all the data from a wikipedia article
        about a snake. Builds a dict that the .get() method can use.

        Created by Ava and eivl for the very first code jam on PythonDiscord.

        :param name: The name of the snake to get information for - omit for a random snake
        :return: A dict containing information on a snake
        """

        snake_info = {}

        async with aiohttp.ClientSession() as session:
            params = {
                'format': 'json',
                'action': 'query',
                'list': 'search',
                'srsearch': name,
                'utf8': '',
                'srlimit': '1',
            }

            json = await self._fetch(session, URL, params=params)

            # wikipedia does have a error page
            try:
                pageid = json["query"]["search"][0]["pageid"]
            except KeyError:
                # Wikipedia error page ID(?)
                pageid = 41118

            params = {
                'format': 'json',
                'action': 'query',
                'prop': 'extracts|images|info',
                'exlimit': 'max',
                'explaintext': '',
                'inprop': 'url',
                'pageids': pageid
            }

            json = await self._fetch(session, URL, params=params)

            # constructing dict - handle exceptions later
            try:
                snake_info["title"] = json["query"]["pages"][f"{pageid}"]["title"]
                snake_info["extract"] = json["query"]["pages"][f"{pageid}"]["extract"]
                snake_info["images"] = json["query"]["pages"][f"{pageid}"]["images"]
                snake_info["fullurl"] = json["query"]["pages"][f"{pageid}"]["fullurl"]
                snake_info["pageid"] = json["query"]["pages"][f"{pageid}"]["pageid"]
            except KeyError:
                snake_info["error"] = True

            if snake_info["images"]:
                i_url = 'https://commons.wikimedia.org/wiki/Special:FilePath/'
                image_list = []
                map_list = []
                thumb_list = []

                # Wikipedia has arbitrary images that are not snakes
                banned = [
                    'Commons-logo.svg',
                    'Red%20Pencil%20Icon.png',
                    'distribution',
                    'The%20Death%20of%20Cleopatra%20arthur.jpg',
                    'Head%20of%20holotype',
                    'locator',
                    'Woma.png',
                    '-map.',
                    '.svg',
                    'ange.',
                    'Adder%20(PSF).png'
                ]

                for image in snake_info["images"]:
                    # images come in the format of `File:filename.extension`
                    file, sep, filename = image["title"].partition(':')
                    filename = filename.replace(" ", "%20")  # Wikipedia returns good data!

                    if not filename.startswith('Map'):
                        if any(ban in filename for ban in banned):
                            pass
                        else:
                            image_list.append(f"{i_url}{filename}")
                            thumb_list.append(f"{i_url}{filename}?width=100")
                    else:
                        map_list.append(f"{i_url}{filename}")

            snake_info["image_list"] = image_list
            snake_info["map_list"] = map_list
            snake_info["thumb_list"] = thumb_list
        return snake_info

    @command(name="snakes.get()", aliases=["snakes.get"])
    @bot_has_permissions(manage_messages=True)
    @locked()
    async def get(self, ctx: Context, name: Snake = None):
        """
        Fetches information about a snake from Wikipedia.
        :param ctx: Context object passed from discord.py
        :param name: Optional, the name of the snake to get information for - omit for a random snake

        Created by Ava and eivl
        """

        with ctx.typing():
            if name is None:
                name = await Snake.random()

            data = await self.get_snek(name)

            if data.get('error'):
                return await ctx.send('Could not fetch data from Wikipedia.')

            match = self.wiki_brief.match(data['extract'])
            description = match.group(1) if match else None
            description = description.replace("\n", "\n\n")  # Give us some proper paragraphs.

            # Shorten the description if needed
            if len(description) > 1000:
                description = description[:1000]
                last_newline = description.rfind("\n")
                if last_newline > 0:
                    description = description[:last_newline]

            # Strip and add the Wiki link.
            description = description.strip("\n")
            description += f"\n\nRead more on [Wikipedia]({data['fullurl']})"

            # Build and send the embed.
            embed = Embed(
                title=data['title'],
                description=description,
                colour=0x59982F,
            )

            emoji = 'https://emojipedia-us.s3.amazonaws.com/thumbs/60/google/3/snake_1f40d.png'
            image = next((url for url in data['image_list'] if url.endswith(self.valid)), emoji)
            embed.set_image(url=image)

            await ctx.send(embed=embed)

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

    async def get_snake_name(self) -> Dict[str, str]:
        """
        Gets a random snake name.
        :return: A random snake name, as a string.
        """

        response = await self.bot.http_session.get(self.names_url, headers=self.headers)
        name_data = await response.json()

        return name_data

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

        snake_name = await self.get_snake_name()
        snake_name = snake_name['name']
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

        # Now, get the index of the vowel to slice the snake_name at
        snake_slice_index = 0
        for index, char in enumerate(snake_name):
            if index == 0:
                continue
            if char.lower() in "aeiouy":
                snake_slice_index = index + 1
                break

        # Combine!
        snake_name = snake_name[snake_slice_index:]
        user_name = user_name[:user_slice_index]
        result = f"{snake_prefix} {user_name}{snake_name}"
        result = string.capwords(result)

        # Embed and send
        embed = Embed(
            title="Snake name",
            description=f"Your snake-name is **{result}**",
            color=SNAKE_COLOR
        )

        return await ctx.send(embed=embed)

    @bot_has_permissions(manage_messages=True)
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

        def event_check(reaction_: Reaction, user_: Member):
            """
            Make sure that this reaction is what we want to operate on
            """
            return (
                all((
                    reaction_.message.id == board_id.id,  # Reaction is on this message
                    reaction_.emoji in ANTIDOTE_EMOJI,    # Reaction is one of the pagination emotes
                    user_.id != self.bot.user.id,         # Reaction was not made by the Bot
                    user_.id == ctx.author.id             # Reaction was made by author
                ))
            )

        # Initialize variables
        antidote_tries = 0
        antidote_guess_count = 0
        antidote_guess_list = []
        guess_result = []
        board = []
        page_guess_list = []
        page_result_list = []
        win = False

        antidote_embed = Embed(color=SNAKE_COLOR, title="Antidote")
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
            antidote_embed = Embed(color=SNAKE_COLOR, title="Antidote")
            antidote_embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
            antidote_embed.set_image(url="https://i.makeagif.com/media/7-12-2015/Cj1pts.gif")
            antidote_embed.add_field(name=f"You have created the snake antidote!",
                                     value=f"The solution was: {' '.join(antidote_answer)}\n"
                                           f"You had {10 - antidote_tries} tries remaining.")
            await board_id.edit(embed=antidote_embed)
        else:
            antidote_embed = Embed(color=SNAKE_COLOR, title="Antidote")
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
            color=SNAKE_COLOR,
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
            color=SNAKE_COLOR
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
    async def snakify(self, ctx: Context, message: str = None):
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

        with ctx.typing():
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
        response = await self.bot.http_session.get(self.facts_url, headers=self.headers)
        question = await response.json()

        # Build and send the embed.
        embed = Embed(
            title="Snake fact",
            color=SNAKE_COLOR,
            description=question
        )
        await ctx.channel.send(embed=embed)

    @command(name="snakes.draw()", aliases=["snakes.draw"])
    async def draw(self, ctx: Context):
        """
        Draws a random snek using Perlin noise

        Made by Momo and kel during the first code jam.
        """

        def beautiful_pastel(hue):
            """
            Returns random bright pastels.
            """

            light = random.uniform(0.7, 0.85)
            saturation = 1

            rgb = colorsys.hls_to_rgb(hue, light, saturation)
            hex_rgb = ""

            for part in rgb:
                value = int(part * 0xFF)
                hex_rgb += f"{value:02x}"

            return int(hex_rgb, 16)

        with ctx.typing():

            # Generate random snake attributes
            width = random.randint(6, 10)
            length = random.randint(15, 22)
            random_hue = random.random()
            snek_color = beautiful_pastel(random_hue)
            text_color = beautiful_pastel((random_hue + 0.5) % 1)
            bg_color = (
                random.randint(32, 50),
                random.randint(32, 50),
                random.randint(50, 70),
            )

            # Get a snake idiom from the API
            response = await self.bot.http_session.get(self.idioms_url, headers=self.headers)
            text = await response.json()

            # Build and send the snek
            factory = perlin.PerlinNoiseFactory(dimension=1, octaves=2)
            image_frame = perlinsneks.create_snek_frame(
                factory,
                snake_width=width,
                snake_length=length,
                snake_color=snek_color,
                text=text,
                text_color=text_color,
                bg_color=bg_color
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
            snake = await self.get_snake_name()
            query = snake['name']

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
        if len(data) > 0:
            num = random.randint(0, len(data) - 1)
            youtube_base_url = 'https://www.youtube.com/watch?v='
            await ctx.channel.send(
                content=f"{youtube_base_url}{data[num]['id']['videoId']}"
            )
        else:
            log.warning(f"CRITICAL ERROR: YouTube API returned {response}")

    @command(name="snakes.sal()", aliases=["snakes.sal"])
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

        # CREATE #
        # check if there is already a game in this channel
        if ctx.channel in self.active_sal:
            await ctx.send(f"{ctx.author.mention} A game is already in progress in this channel.")
            return

        game = sal.SnakeAndLaddersGame(snakes=self, context=ctx)
        self.active_sal[ctx.channel] = game

        await game.open_game()

    @command(name="snakes.movie()", aliases=["movie"])
    async def movie(self, ctx: Context):
        """
        Gets a random snake-related movie from OMDB.

        Written by Samuel and Fat & Proud during the very first code jam.
        Modified by gdude for inclusion in the bot.
        """

        url = "http://www.omdbapi.com/"
        page = random.randint(1, 27)

        response = await self.bot.http_session.get(
            url,
            params={
                "s": "snake",
                "page": page,
                "type": "movie",
                "apikey": OMDB_API_KEY
            }
        )
        data = await response.json()
        movie = random.choice(data["Search"])["imdbID"]

        response = await self.bot.http_session.get(
            url,
            params={
                "i": movie,
                "apikey": OMDB_API_KEY
            }
        )
        data = await response.json()

        embed = Embed(
            title=data["Title"],
            color=SNAKE_COLOR
        )

        del data["Response"], data["imdbID"], data["Title"]

        for key, value in data.items():
            if not value or value == "N/A" or key in ("Response", "imdbID", "Title", "Type"):
                continue

            if key == "Ratings":  # [{'Source': 'Internet Movie Database', 'Value': '7.6/10'}]
                rating = random.choice(value)

                if rating["Source"] != "Internet Movie Database":
                    embed.add_field(name=f"Rating: {rating['Source']}", value=rating["Value"])

                continue

            if key == "Poster":
                embed.set_image(url=value)
                continue

            elif key == "imdbRating":
                key = "IMDB Rating"

            elif key == "imdbVotes":
                key = "IMDB Votes"

            embed.add_field(name=key, value=value, inline=True)

        embed.set_footer(text="Data provided by the OMDB API")

        await ctx.channel.send(
            embed=embed
        )


def setup(bot):
    bot.add_cog(Snakes(bot))
    log.info("Cog loaded: Snakes")
