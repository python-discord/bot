import asyncio
import discord
import random
import numpy
import collections
import pymongo 

from discord.ext import commands
from bot.bot import Bot

class Games(commands.Cog):
    def __init__(self, bot):
        self.bot = bot  

    @commands.cooldown(1, 3, commands.BucketType.user)
    async def slots(self, ctx):        
        # Creates a Dictionary that matches the Emoji and Exp
        symbolTable = {
                '💚':100,
                '💛':50,
                '❤️':10,
                }

        emojis = ['💚', '💛', '❤️']
        probability = ['0.25', '0.35', '0.4']
        roll = numpy.random.choice(emojis, 3, p=probability)
        
        # Creates a Counter that counts the Emoji in a Dictionary
        counter = collections.Counter(roll)
        key = counter.keys()
        value = counter.values()
        
        expList = []
        # Matching Emoji to Dictionary
        for x, y in zip(key, value):
            exp = symbolTable[x]
            expList.append(exp*y)
        totalXp = sum(expList)

        embed = discord.Embed(description=f'**---------------------\n | {roll[0]} | {roll[1]} | {roll[2]} |\n ---------------------**\n', color=discord.Color.from_hsv(random.random(), 1, 1))
        embed.set_author(name='Slot XP Machine', icon_url=ctx.author.avatar_url)
        embed.add_field(name='📤 Money Gained', value=f'**{totalXp}**')
        return await ctx.send(embed=embed)
        
    @slots.error
    async def slots_error(self, ctx, error):  
        if isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(f'{ctx.author.mention} Kindly try again in **{error.retry_after:.2}s**.') 
           
    
# Adding the cog to main script
def setup(bot: Bot) -> None:
    bot.add_cog(Games(bot))            