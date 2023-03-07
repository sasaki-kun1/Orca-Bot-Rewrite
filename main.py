# import libraries
import asyncio
import discord
import sys
import math
import os

# import Necesssary Utilities
from discord.ext import commands
from discord import app_commands
from discord.utils import get

# basic Discord Bot Necessities
intents = discord.Intents.all()
intents.members = True
client = commands.Bot(command_prefix = "`", intents = intents, help_command = None)

# Load All Cogs
async def load():
    loaded_cogs = 0
    failed_cogs = []
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                await client.load_extension(f'cogs.{filename[:-3]}')
                loaded_cogs += 1
            except Exception as e:
                print(f"Failed to load extension {filename}: {e}")
                failed_cogs.append(filename)
    print(f"Loaded {loaded_cogs} cogs successfully.")
    if failed_cogs:
        print(f"Failed to load {len(failed_cogs)} cog(s): {', '.join(failed_cogs)}")
    else:
        print("All cogs loaded successfully.")

# Run the Client
async def main():
    for attempt in range(2):
        try:
            await load()
            await client.start('ODIzNjk3ODMxMjgxNTU3NTM0.GVG02u.kZDO0hvEpdlcEY5nEYeHU9mR-E7jRVqnu9fts4')
        except Exception as e:
            print(f"Failed to start bot: {e}")
            if attempt == 0:
                print("Retrying...")
            else:
                print("Failed to load again. Check the server and restart.")
                break

if __name__ == '__main__':
    asyncio.run(main())
