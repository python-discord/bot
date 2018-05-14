BOARD_TILE_SIZE = 56  # the size of each board tile
BOARD_PLAYER_SIZE = 20  # the size of each player icon
BOARD_MARGIN = (10, 0)  # margins, in pixels (for player icons)
PLAYER_ICON_IMAGE_SIZE = 32  # the size of the image to download, should a power of 2 and higher than BOARD_PLAYER_SIZE
MAX_PLAYERS = 4  # depends on the board size/quality, 4 is for the default board

# board definition (from, to)
BOARD = {
    # ladders
    2: 38,
    7: 14,
    8: 31,
    15: 26,
    21: 42,
    28: 84,
    36: 44,
    51: 67,
    71: 91,
    78: 98,
    87: 94,

    # snakes
    99: 80,
    95: 75,
    92: 88,
    89: 68,
    74: 53,
    64: 60,
    62: 19,
    49: 11,
    46: 25,
    16: 6
}
