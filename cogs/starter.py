import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime

# this class is responsible for starting and syncing the bot and commands
class starter(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        await self.client.tree.sync()
        print("Bot is online")
        print('Logged as:\n{0.user.name}\n{0.user.id}\n------------------'.format(self.client))
        await self.client.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="MAINTENANCE"))

async def setup(client):
    await client.add_cog(starter(client))
