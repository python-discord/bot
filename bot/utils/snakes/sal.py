import io
import math
import os
import random

import aiohttp
import discord
from PIL import Image

from bot.utils.snakes.sal_board import (
    BOARD, BOARD_MARGIN, BOARD_PLAYER_SIZE,
    BOARD_TILE_SIZE, MAX_PLAYERS, PLAYER_ICON_IMAGE_SIZE
)


class SnakeAndLaddersGame:
    def __init__(self, snakes, channel: discord.TextChannel, author: discord.Member):
        self.snakes = snakes
        self.channel = channel
        self.state = 'booting'
        self.author = author
        self.players = []
        self.player_tiles = {}
        self.round_has_rolled = {}
        self.avatar_images = {}

    async def open_game(self):
        await self._add_player(self.author)
        await self.channel.send(
            '**Snakes and Ladders**: A new game is about to start!\nMention me and type **sal join** to participate.',
            file=discord.File(os.path.join('res', 'ladders', 'banner.jpg'), filename='Snakes and Ladders.jpg'))
        self.state = 'waiting'

    async def _add_player(self, user: discord.Member):
        self.players.append(user)
        self.player_tiles[user.id] = 1
        avatar_url = user.avatar_url_as(format='jpeg', size=PLAYER_ICON_IMAGE_SIZE)
        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url) as res:
                avatar_bytes = await res.read()
                im = Image.open(io.BytesIO(avatar_bytes)).resize((BOARD_PLAYER_SIZE, BOARD_PLAYER_SIZE))
                self.avatar_images[user.id] = im

    async def player_join(self, user: discord.Member):
        for p in self.players:
            if user == p:
                await self.channel.send(user.mention + " You are already in the game.")
                return
        if self.state != 'waiting':
            await self.channel.send(user.mention + " You cannot join at this time.")
            return
        if len(self.players) is MAX_PLAYERS:
            await self.channel.send(user.mention + " The game is full!")
            return

        await self._add_player(user)

        await self.channel.send(
            "**Snakes and Ladders**: " + user.mention + " has joined the game.\nThere are now " + str(
                len(self.players)) + " players in the game.")

    async def player_leave(self, user: discord.Member):
        if user == self.author:
            await self.channel.send(user.mention + " You are the author, and cannot leave the game. Execute "
                                                   "`sal cancel` to cancel the game.")
            return
        for p in self.players:
            if user == p:
                self.players.remove(p)
                self.player_tiles.pop(p.id, None)
                self.round_has_rolled.pop(p.id, None)
                await self.channel.send("**Snakes and Ladders**: " + user.mention + " has left the game.")
                if self.state != 'waiting' and len(self.players) == 1:
                    await self.channel.send("**Snakes and Ladders**: The game has been surrendered!")
                    self._destruct()
                return
        await self.channel.send(user.mention + " You are not in the match.")

    async def cancel_game(self, user: discord.Member):
        if not user == self.author:
            await self.channel.send(user.mention + " Only the author of the game can cancel it.")
            return
        await self.channel.send("**Snakes and Ladders**: Game has been canceled.")
        self._destruct()

    async def start_game(self, user: discord.Member):
        if not user == self.author:
            await self.channel.send(user.mention + " Only the author of the game can start it.")
            return
        if len(self.players) < 2:
            await self.channel.send(user.mention + " A minimum of 2 players is required to start the game.")
            return
        if not self.state == 'waiting':
            await self.channel.send(user.mention + " The game cannot be started at this time.")
            return
        self.state = 'starting'
        player_list = ', '.join(user.mention for user in self.players)
        await self.channel.send("**Snakes and Ladders**: The game is starting!\nPlayers: " + player_list)
        await self.start_round()

    async def start_round(self):
        self.state = 'roll'
        for user in self.players:
            self.round_has_rolled[user.id] = False
        board_img = Image.open(os.path.join('res', 'ladders', 'board.jpg'))
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
        board_file = discord.File(stream.getvalue(), filename='Board.jpg')
        await self.channel.send("**Snakes and Ladders**: A new round has started! Current board:", file=board_file)
        player_list = '\n'.join((user.mention + ": Tile " + str(self.player_tiles[user.id])) for user in self.players)
        await self.channel.send(
            "**Current positions**:\n" + player_list + "\n\nMention me with **roll** to roll the dice!")

    async def player_roll(self, user: discord.Member):
        if user.id not in self.player_tiles:
            await self.channel.send(user.mention + " You are not in the match.")
            return
        if self.state != 'roll':
            await self.channel.send(user.mention + " You may not roll at this time.")
            return
        if self.round_has_rolled[user.id]:
            return
        roll = random.randint(1, 6)
        await self.channel.send(user.mention + " rolled a **{0}**!".format(roll))
        next_tile = self.player_tiles[user.id] + roll
        # apply snakes and ladders
        if next_tile in BOARD:
            target = BOARD[next_tile]
            if target < next_tile:
                await self.channel.send(user.mention + " slips on a snake and falls back to **{0}**".format(target))
            else:
                await self.channel.send(user.mention + " climbs a ladder to **{0}**".format(target))
            next_tile = target

        self.player_tiles[user.id] = min(100, next_tile)
        self.round_has_rolled[user.id] = True
        if self._check_all_rolled():
            await self._complete_round()

    async def _complete_round(self):
        self.state = 'post_round'
        # check for winner
        winner = self._check_winner()
        if winner is None:
            # there is a winner, start the next round
            await self.start_round()
            return
        # announce winner and exit
        await self.channel.send("**Snakes and Ladders**: " + winner.mention + " has won the game! :tada:")
        self._destruct()

    def _check_winner(self) -> discord.Member:
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
