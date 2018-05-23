import asyncio
import io
import logging
import math
import os
import random

import aiohttp
from discord import File, Member, Reaction
from discord.ext.commands import Context
from PIL import Image

from bot.utils.snakes.sal_board import (
    BOARD, BOARD_MARGIN, BOARD_PLAYER_SIZE,
    BOARD_TILE_SIZE, MAX_PLAYERS, PLAYER_ICON_IMAGE_SIZE
)

log = logging.getLogger(__name__)

# Emoji constants
START_EMOJI = "\u2611"     # :ballot_box_with_check: - Start the game
CANCEL_EMOJI = "\u274C"    # :x: - Cancel or leave the game
ROLL_EMOJI = "\U0001F3B2"  # :game_die: - Roll the die!
JOIN_EMOJI = "\U0001F64B"  # :raising_hand: - Join the game.

STARTUP_SCREEN_EMOJI = [
    JOIN_EMOJI,
    START_EMOJI,
    CANCEL_EMOJI
]

GAME_SCREEN_EMOJI = [
    ROLL_EMOJI,
    CANCEL_EMOJI
]


class SnakeAndLaddersGame:
    def __init__(self, snakes, context: Context):
        self.snakes = snakes
        self.ctx = context
        self.channel = self.ctx.channel
        self.state = 'booting'
        self.started = False
        self.author = self.ctx.author
        self.players = []
        self.player_tiles = {}
        self.round_has_rolled = {}
        self.avatar_images = {}
        self.board = None
        self.positions = None
        self.rolls = []

    async def open_game(self):
        """
        Create a new Snakes and Ladders game.

        Listen for reactions until players have joined,
        and the game has been started.
        """

        def startup_event_check(reaction_: Reaction, user_: Member):
            """
            Make sure that this reaction is what we want to operate on
            """
            return (
                all((
                    reaction_.message.id == startup.id,       # Reaction is on startup message
                    reaction_.emoji in STARTUP_SCREEN_EMOJI,  # Reaction is one of the startup emotes
                    user_.id != self.ctx.bot.user.id,         # Reaction was not made by the bot
                ))
            )

        # Check to see if the bot can remove reactions
        if not self.channel.permissions_for(self.ctx.guild.me).manage_messages:
            log.warning(
                "Unable to start Snakes and Ladders - "
                f"Missing manage_messages permissions in {self.channel}"
            )
            return

        await self._add_player(self.author)
        await self.channel.send(
            "**Snakes and Ladders**: A new game is about to start!",
            file=File(
                os.path.join("bot", "resources", "snakes_and_ladders", "banner.jpg"),
                filename='Snakes and Ladders.jpg'
            )
        )
        startup = await self.channel.send(
            f"Press {JOIN_EMOJI} to participate, and press "
            f"{START_EMOJI} to start the game"
        )
        for emoji in STARTUP_SCREEN_EMOJI:
            await startup.add_reaction(emoji)

        self.state = 'waiting'

        while not self.started:
            try:
                reaction, user = await self.ctx.bot.wait_for(
                    "reaction_add",
                    timeout=300,
                    check=startup_event_check
                )
                if reaction.emoji == JOIN_EMOJI:
                    await self.player_join(user)
                elif reaction.emoji == CANCEL_EMOJI:
                    if self.ctx.author == user:
                        await self.cancel_game(user)
                        return
                    else:
                        await self.player_leave(user)
                elif reaction.emoji == START_EMOJI:
                    if self.ctx.author == user:
                        self.started = True
                        await self.start_game(user)
                        await startup.delete()
                        break

                await startup.remove_reaction(reaction.emoji, user)

            except asyncio.TimeoutError:
                log.debug("Snakes and Ladders timed out waiting for a reaction")
                self.cancel_game(self.author)
                return  # We're done, no reactions for the last 5 minutes

    async def _add_player(self, user: Member):
        self.players.append(user)
        self.player_tiles[user.id] = 1
        avatar_url = user.avatar_url_as(format='jpeg', size=PLAYER_ICON_IMAGE_SIZE)
        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url) as res:
                avatar_bytes = await res.read()
                im = Image.open(io.BytesIO(avatar_bytes)).resize((BOARD_PLAYER_SIZE, BOARD_PLAYER_SIZE))
                self.avatar_images[user.id] = im

    async def player_join(self, user: Member):
        for p in self.players:
            if user == p:
                await self.channel.send(user.mention + " You are already in the game.", delete_after=10)
                return
        if self.state != 'waiting':
            await self.channel.send(user.mention + " You cannot join at this time.", delete_after=10)
            return
        if len(self.players) is MAX_PLAYERS:
            await self.channel.send(user.mention + " The game is full!", delete_after=10)
            return

        await self._add_player(user)

        await self.channel.send(
            f"**Snakes and Ladders**: {user.mention} has joined the game.\n"
            f"There are now {str(len(self.players))} players in the game.",
            delete_after=10
        )

    async def player_leave(self, user: Member):
        if user == self.author:
            await self.channel.send(
                user.mention + " You are the author, and cannot leave the game. Execute "
                "`sal cancel` to cancel the game.",
                delete_after=10
            )
            return
        for p in self.players:
            if user == p:
                self.players.remove(p)
                self.player_tiles.pop(p.id, None)
                self.round_has_rolled.pop(p.id, None)
                await self.channel.send(
                    "**Snakes and Ladders**: " + user.mention + " has left the game.",
                    delete_after=10
                )

                if self.state != 'waiting' and len(self.players) == 1:
                    await self.channel.send("**Snakes and Ladders**: The game has been surrendered!")
                    self._destruct()
                return
        await self.channel.send(user.mention + " You are not in the match.", delete_after=10)

    async def cancel_game(self, user: Member):
        if not user == self.author:
            await self.channel.send(user.mention + " Only the author of the game can cancel it.", delete_after=10)
            return
        await self.channel.send("**Snakes and Ladders**: Game has been canceled.")
        self._destruct()

    async def start_game(self, user: Member):
        if not user == self.author:
            await self.channel.send(user.mention + " Only the author of the game can start it.", delete_after=10)
            return
        if len(self.players) < 1:
            await self.channel.send(
                user.mention + " A minimum of 2 players is required to start the game.",
                delete_after=10
            )
            return
        if not self.state == 'waiting':
            await self.channel.send(user.mention + " The game cannot be started at this time.", delete_after=10)
            return
        self.state = 'starting'
        player_list = ', '.join(user.mention for user in self.players)
        await self.channel.send("**Snakes and Ladders**: The game is starting!\nPlayers: " + player_list)
        await self.start_round()

    async def start_round(self):

        def game_event_check(reaction_: Reaction, user_: Member):
            """
            Make sure that this reaction is what we want to operate on
            """
            return (
                all((
                    reaction_.message.id == self.positions.id,  # Reaction is on positions message
                    reaction_.emoji in GAME_SCREEN_EMOJI,       # Reaction is one of the game emotes
                    user_.id != self.ctx.bot.user.id,           # Reaction was not made by the bot
                ))
            )

        self.state = 'roll'
        for user in self.players:
            self.round_has_rolled[user.id] = False
        board_img = Image.open(os.path.join("bot", "resources", "snakes_and_ladders", "board.jpg"))
        player_row_size = math.ceil(MAX_PLAYERS / 2)

        for i, player in enumerate(self.players):
            tile = self.player_tiles[player.id]
            tile_coordinates = self._board_coordinate_from_index(tile)
            x_offset = BOARD_MARGIN[0] + tile_coordinates[0] * BOARD_TILE_SIZE
            y_offset = \
                BOARD_MARGIN[1] + (
                    (10 * BOARD_TILE_SIZE) - (9 - tile_coordinates[1]) * BOARD_TILE_SIZE - BOARD_PLAYER_SIZE)
            x_offset += BOARD_PLAYER_SIZE * (i % player_row_size)
            y_offset -= BOARD_PLAYER_SIZE * math.floor(i / player_row_size)
            board_img.paste(self.avatar_images[player.id],
                            box=(x_offset, y_offset))
        stream = io.BytesIO()
        board_img.save(stream, format='JPEG')
        board_file = File(stream.getvalue(), filename='Board.jpg')
        player_list = '\n'.join((user.mention + ": Tile " + str(self.player_tiles[user.id])) for user in self.players)

        # Store and send new messages
        temp_board = await self.channel.send(
            "**Snakes and Ladders**: A new round has started! Current board:",
            file=board_file
        )
        temp_positions = await self.channel.send(
            f"**Current positions**:\n{player_list}\n\nUse {ROLL_EMOJI} to roll the dice!"
        )

        # Delete the previous messages
        if self.board and self.positions:
            await self.board.delete()
            await self.positions.delete()

        # remove the roll messages
        for roll in self.rolls:
            await roll.delete()
        self.rolls = []

        # Save new messages
        self.board = temp_board
        self.positions = temp_positions

        # Wait for rolls
        for emoji in GAME_SCREEN_EMOJI:
            await self.positions.add_reaction(emoji)

        while True:
            try:
                reaction, user = await self.ctx.bot.wait_for(
                    "reaction_add",
                    timeout=300,
                    check=game_event_check
                )

                if reaction.emoji == ROLL_EMOJI:
                    await self.player_roll(user)
                elif reaction.emoji == CANCEL_EMOJI:
                    if self.ctx.author == user:
                        await self.cancel_game(user)
                        return
                    else:
                        await self.player_leave(user)

                await self.positions.remove_reaction(reaction.emoji, user)

                if self._check_all_rolled():
                    break

            except asyncio.TimeoutError:
                log.debug("Snakes and Ladders timed out waiting for a reaction")
                await self.cancel_game(self.author)
                return  # We're done, no reactions for the last 5 minutes

        # Round completed
        await self._complete_round()

    async def player_roll(self, user: Member):
        if user.id not in self.player_tiles:
            await self.channel.send(user.mention + " You are not in the match.", delete_after=10)
            return
        if self.state != 'roll':
            await self.channel.send(user.mention + " You may not roll at this time.", delete_after=10)
            return
        if self.round_has_rolled[user.id]:
            return
        roll = random.randint(1, 6)
        self.rolls.append(await self.channel.send(f"{user.mention} rolled a **{roll}**!"))
        next_tile = self.player_tiles[user.id] + roll

        # apply snakes and ladders
        if next_tile in BOARD:
            target = BOARD[next_tile]
            if target < next_tile:
                await self.channel.send(
                    f"{user.mention} slips on a snake and falls back to **{target}**",
                    delete_after=15
                )
            else:
                await self.channel.send(
                    f"{user.mention} climbs a ladder to **{target}**",
                    delete_after=15
                )
            next_tile = target

        self.player_tiles[user.id] = min(100, next_tile)
        self.round_has_rolled[user.id] = True

    async def _complete_round(self):

        self.state = 'post_round'

        # check for winner
        winner = self._check_winner()
        if winner is None:
            # there is no winner, start the next round
            await self.start_round()
            return

        # announce winner and exit
        await self.channel.send("**Snakes and Ladders**: " + winner.mention + " has won the game! :tada:")
        self._destruct()

    def _check_winner(self) -> Member:
        if self.state != 'post_round':
            return None
        return next((player for player in self.players if self.player_tiles[player.id] == 100),
                    None)

    def _check_all_rolled(self):
        return all(rolled for rolled in self.round_has_rolled.values())

    def _destruct(self):
        del self.snakes.active_sal[self.channel]

    def _board_coordinate_from_index(self, index: int):
        # converts the tile number to the x/y coordinates for graphical purposes
        y_level = 9 - math.floor((index - 1) / 10)
        is_reversed = math.floor((index - 1) / 10) % 2 != 0
        x_level = (index - 1) % 10
        if is_reversed:
            x_level = 9 - x_level
        return x_level, y_level
