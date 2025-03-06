import discord
from discord.ext import commands


async def send_dm(user, message: str):
    """Sends a DM to the user object"""
    try:
        await user.send(message)

    except discord.NotFound:
        print("User not found.")
    except discord.Forbidden:
        print("Permission denied.")
    except discord.HTTPException:
        print("Failed to send DM: HTTP Error")