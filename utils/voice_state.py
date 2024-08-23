import discord
from discord.ext import commands
import asyncio
import math
import itertools
import random
from async_timeout import timeout
from datetime import datetime
import gc
from utils.views import QueuePages, NowPlayingButtons
from utils.yt_source import YTDLSource, Song, YTDLError, VoiceError

class SongQueue(asyncio.Queue):
    def __getitem__(self, item):
        if isinstance(item, slice):
            return list(itertools.islice(self._queue, item.start, item.stop, item.step))
        else:
            return self._queue[item]

    def __iter__(self):
        return self._queue.__iter__()

    def __len__(self):
        return self.qsize()

    def clear(self):
        self._queue.clear()

    def shuffle(self):
        random.shuffle(self._queue)

    def remove(self, index: int):
        del self._queue[index]

class VoiceState:
    def __init__(self, bot: commands.Bot, ctx: commands.Context):
        self.bot = bot
        self._ctx = ctx
        self.exists = True
        self.current = None
        self.voice = None
        self.next = asyncio.Event()
        self.songs = SongQueue()
        self._loop = False
        self._volume = 0.3  # Default volume set to 30%
        self.skip_votes = set()
        self.audio_player = bot.loop.create_task(self.audio_player_task())
        self.now_playing_message = None
        self.queue_message = None
        self.first_song_played = False
        self.action_message = ""  # To store the action message
        self.inactivity_task = bot.loop.create_task(self.inactivity_timer())  # Add inactivity timer
        self.last_added_message = None  # Track the last added message
        self.lock = asyncio.Lock()  # Initialize the lock

    async def add_song(self, song):
        await self.songs.put(song)
        await self.add_song_message(song)
    def __del__(self):
        self.audio_player.cancel()

    @property
    def loop(self):
        return self._loop

    @loop.setter
    def loop(self, value: bool):
        self._loop = value

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value: float):
        self._volume = value

    @property
    def is_playing(self):
        return self.voice and self.current

    async def change_volume(self, delta: int, interaction: discord.Interaction):
        new_volume = self._volume + (delta / 100)
        new_volume = max(0, min(1, new_volume))  # Ensure the volume is between 0 and 1
        self._volume = new_volume
        if self.current:
            self.current.source.volume = self._volume

        # Update the Now Playing embed with the volume change notification
        self.action_message = f"**{interaction.user.display_name} changed the volume to {int(self._volume * 100)}%**"
        await self.update_now_playing_embed(interaction)

    async def audio_player_task(self):
        while True:
            self.next.clear()
            if not self.loop or not self.current:
                try:
                    async with timeout(None):
                        self.current = await self.songs.get()
                except asyncio.TimeoutError:
                    self.bot.loop.create_task(self.stop())
                    self.exists = False
                    return

            self.current.source.volume = self._volume
            async with self.lock:  # Ensure this section is thread-safe
                self.voice.play(self.current.source, after=self.play_next_song)

            await self.update_now_playing_embed()  # Ensure this is called after playback starts

            self.first_song_played = True
            await self.next.wait()

            if self.loop and self.current:
                await self.songs.put(self.current)

            self.bot.loop.create_task(self.update_queue_message())

    def play_next_song(self, error=None):
        if error:
            print(f'Error in play_next_song: {error}')
            raise VoiceError(str(error))
        self.next.set()

    def skip(self):
        self.skip_votes.clear()
        if self.is_playing:
            self.voice.stop()

    async def stop(self):
        self.songs.clear()
        if self.voice:
            await self.voice.disconnect()
            self.voice = None
        self.exists = False
        if self.queue_message:
            await self.queue_message.edit(content="Bot disconnected from the voice channel. Stopping playlist processing.", embed=None, view=None)

    async def update_queue_message(self):
        if not self.first_song_played:
            return

        ctx = self._ctx
        items_per_page = 10
        pages = math.ceil(len(self.songs) / items_per_page)
        start = 0
        end = items_per_page
        embeds = []

        if len(self.songs) == 0:
            embed = discord.Embed(description='**Empty queue.**')
            embeds.append(embed)
        else:
            for page in range(pages):
                queue = ''
                for i, song in enumerate(self.songs[page * items_per_page:(page + 1) * items_per_page], start=page * items_per_page):
                    queue += '`{0}.` [**{1.source.title}**]({1.source.url})\n'.format(i + 1, song)
                embed = (discord.Embed(description='**{} track(s):**\n\n{}'.format(len(self.songs), queue))
                         .set_footer(text='Viewing page {}/{}'.format(page + 1, pages)))
                embeds.append(embed)

        view = QueuePages(ctx, embeds, current_page=0)
        try:
            if self.queue_message:
                await self.queue_message.edit(embed=embeds[0], view=view)
            else:
                self.queue_message = await ctx.send(embed=embeds[0], view=view)
        except discord.errors.HTTPException as e:
            if e.status == 401:
                print("Invalid Webhook Token. Unable to edit queue message.")
                self.queue_message = None
            else:
                raise

    async def ensure_queue_message_valid(self):
        if self.queue_message:
            try:
                await self.queue_message.edit(content="Queue updated.")
            except discord.NotFound:
                self.queue_message = None
        await self.update_queue_message()

    async def update_now_playing_embed(self, interaction=None):
        ctx = self._ctx
        if self.current is None:
            return  # Exit if there is no current song
        embed = self.current.create_embed()
        if self.action_message:
            embed.add_field(name="Action:", value=self.action_message, inline=False)
        try:
            if self.now_playing_message:
                self.now_playing_message = await ctx.fetch_message(self.now_playing_message.id)  # Re-fetch the message
                await self.now_playing_message.edit(embed=embed, view=NowPlayingButtons(ctx))
            else:
                self.now_playing_message = await ctx.send(embed=embed, view=NowPlayingButtons(ctx))
        except discord.errors.HTTPException as e:
            print(f"Failed to edit message: {e}")
            self.now_playing_message = await ctx.send(embed=embed, view=NowPlayingButtons(ctx))
        # Clear the action message after updating the embed
        self.action_message = ""



    async def inactivity_timer(self):
        while self.exists:
            await asyncio.sleep(1800)  # 45 minutes

            # Check if there are no songs in the queue and nothing is currently playing
            if not self.is_playing and not self.songs.qsize() > 0:
                # Also check if the bot is connected to a voice channel
                if self.voice is not None:
                    await self._ctx.send("Leaving voice channel due to inactivity.")
                    await self.stop()
                    print("Bot stopped due to inactivity.")
                else:
                    print("Bot was not connected to a voice channel, no need to stop.")
            else:
                print("Bot is active, resetting inactivity timer.")

