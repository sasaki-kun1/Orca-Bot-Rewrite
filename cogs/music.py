import discord
from discord.ext import commands
from datetime import datetime
import gc
import spotipy
import math
from spotipy.oauth2 import SpotifyClientCredentials
from utils.voice_state import VoiceState
from utils.views import QueuePages, ClearQueueConfirmation, NowPlayingButtons
from utils.yt_source import YTDLSource, Song, YTDLError

# Spotify credentials
SPOTIPY_CLIENT_ID = 'CLIENT_HERE'
SPOTIPY_CLIENT_SECRET = 'SECRET_HERE'

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIPY_CLIENT_ID,
    client_secret=SPOTIPY_CLIENT_SECRET,
    requests_session=True,  # Ensure requests_session is properly managed
))

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_states = {}

    def get_voice_state(self, ctx: commands.Context):
        state = self.voice_states.get(ctx.guild.id)
        if not state or not state.exists:
            state = VoiceState(self.bot, ctx)
            self.voice_states[ctx.guild.id] = state
        ctx.voice_state = state  # Add this line to attach voice_state to ctx
        return state

    def cog_unload(self):
        for state in self.voice_states.values():
            self.bot.loop.create_task(state.stop())

    def cog_check(self, ctx: commands.Context):
        if not ctx.guild:
            raise commands.NoPrivateMessage('This command can\'t be used in DM channels.')
        return True

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        await ctx.send('An error occurred: {}'.format(str(error)))

    async def ensure_voice_state(self, ctx: commands.Context):
        ctx.voice_state = self.get_voice_state(ctx)  # Ensure ctx.voice_state is set
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError('You are not connected to any voice channel.')
        if ctx.voice_client:
            if ctx.voice_client.channel != ctx.author.voice.channel:
                raise commands.CommandError('Bot is already in a voice channel.')

    @commands.hybrid_command(name='join', description='Join a voice channel.', invoke_without_subcommand=True)
    async def _join(self, ctx: commands.Context) -> None:
        await self.ensure_voice_state(ctx)
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        server_name = ctx.guild.name
        server_id = ctx.guild.id
        user_hash = ctx.author.discriminator
        destination = ctx.author.voice.channel
        if ctx.voice_state.voice:
            if ctx.voice_state.voice.channel == destination:
                await ctx.send("I am already in your voice channel.")
            else:
                await ctx.voice_state.voice.move_to(destination)
                await ctx.send("I moved to your voice channel.")
        else:
            ctx.voice_state.voice = await destination.connect()
            await ctx.send("I joined your voice channel.")
            print(f'{timestamp} - {ctx.author.display_name}#{user_hash} used the join command in server "{server_name}" ({server_id})')

    @commands.hybrid_command(name='leave', description='Leave the voice channel.', aliases=['disconnect'])
    async def _leave(self, ctx: commands.Context) -> None:
        await self.ensure_voice_state(ctx)
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        server_name = ctx.guild.name
        server_id = ctx.guild.id
        user_hash = ctx.author.discriminator
        if not ctx.voice_state.voice:
            return await ctx.send('Not connected to a voice channel.')
        await ctx.voice_state.stop()
        del self.voice_states[ctx.guild.id]
        print(f'{timestamp} - {ctx.author.display_name}#{user_hash} used the leave command in server "{server_name}" ({server_id})')
        await ctx.send("Left the voice channel.")

    @commands.hybrid_command(name='display', description='Displays the currently playing song.', aliases=['current', 'playing'])
    async def _now(self, ctx: commands.Context) -> None:
        await self.ensure_voice_state(ctx)
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        server_name = ctx.guild.name
        server_id = ctx.guild.id
        user_hash = ctx.author.discriminator
        await ctx.send(embed=ctx.voice_state.current.create_embed())
        print(f'{timestamp} - {ctx.author.display_name}#{user_hash} used the display command in server "{server_name}" ({server_id})')

    @commands.hybrid_command(name='pause', description='Pauses the audio.')
    @commands.has_permissions(manage_guild=True)
    async def _pause(self, ctx: commands.Context) -> None:
        await self.ensure_voice_state(ctx)
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        server_name = ctx.guild.name
        server_id = ctx.guild.id
        user_hash = ctx.author.discriminator
        player = ctx.voice_client
        if player.is_playing():
            player.pause()
            print(f'{timestamp} - {ctx.author.display_name}#{user_hash} used the pause command in server "{server_name}" ({server_id})')
            await ctx.send("I paused the audio.")
        else:
            await ctx.send('No audio is playing currently.')

    @commands.hybrid_command(name='resume', description='Resume the audio')
    @commands.has_permissions(manage_guild=True)
    async def _resume(self, ctx: commands.Context) -> None:
        await self.ensure_voice_state(ctx)
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        server_name = ctx.guild.name
        server_id = ctx.guild.id
        user_hash = ctx.author.discriminator
        player = ctx.voice_client
        if player.is_paused():
            player.resume()
            print(f'{timestamp} - {ctx.author.display_name}#{user_hash} used the resume command in server "{server_name}" ({server_id})')
            await ctx.send("I resumed the audio.")
        else:
            await ctx.send('The audio is already playing.')

    @commands.hybrid_command(name='skip', description='Skips the currently playing audio.')
    async def _skip(self, ctx: commands.Context) -> None:
        await self.ensure_voice_state(ctx)
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        server_name = ctx.guild.name
        server_id = ctx.guild.id
        user_hash = ctx.author.discriminator
        if not ctx.voice_state.is_playing:
            return await ctx.send('No audio is playing.')
        else:
            await ctx.send("Skipped the audio.")
            print(f'{timestamp} - {ctx.author.display_name}#{user_hash} used the skip command in server "{server_name}" ({server_id})')
            ctx.voice_state.skip()

    @commands.hybrid_command(name='queue', description='Shows the queue. You can optionally specify the page to show. Each page contains 10 elements.')
    async def _queue(self, ctx: commands.Context, *, page: int = 1):
        await self.ensure_voice_state(ctx)
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        server_name = ctx.guild.name
        server_id = ctx.guild.id
        user_hash = ctx.author.discriminator
        if len(ctx.voice_state.songs) == 0:
            print(f'{timestamp} - {ctx.author.display_name}#{user_hash} used the queue command in server "{server_name}" ({server_id})')
            return await ctx.send('Empty queue.')

        items_per_page = 10
        pages = math.ceil(len(ctx.voice_state.songs) / items_per_page)
        start = (page - 1) * items_per_page
        end = start + items_per_page
        embeds = []

        for page in range(pages):
            queue = ''
            for i, song in enumerate(ctx.voice_state.songs[page * items_per_page:(page + 1) * items_per_page], start=page * items_per_page):
                queue += '`{0}.` [**{1.source.title}**]({1.source.url})\n'.format(i + 1, song)
            embed = (discord.Embed(description='**{} track(s):**\n\n{}'.format(len(ctx.voice_state.songs), queue))
                    .set_footer(text='Viewing page {}/{}'.format(page + 1, pages)))
            embeds.append(embed)

        view = QueuePages(ctx, embeds, current_page=page - 1)

        if ctx.voice_state.queue_message:
            await ctx.voice_state.queue_message.edit(embed=embeds[page - 1], view=view)
        else:
            ctx.voice_state.queue_message = await ctx.send(embed=embeds[page - 1], view=view)

    @commands.hybrid_command(name='clear', description='Clears the queue.')
    async def _clear(self, ctx: commands.Context):
        await self.ensure_voice_state(ctx)
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        server_name = ctx.guild.name
        server_id = ctx.guild.id
        user_hash = ctx.author.discriminator
        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('The queue is already empty.')
        confirmation_message = await ctx.send("Are you sure you want to clear the queue?", view=ClearQueueConfirmation(ctx, ctx.voice_state))
        print(f'{timestamp} - {ctx.author.display_name}#{user_hash} used the clear command in server "{server_name}" ({server_id})')

    @commands.hybrid_command(name='shuffle', description='Shuffles the queue.')
    async def _shuffle(self, ctx: commands.Context):
        await self.ensure_voice_state(ctx)
        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Empty queue.')
        ctx.voice_state.songs.shuffle()
        await ctx.voice_state.update_queue_message()
        await ctx.send("I shuffled the queue.")
        gc.collect()

    @commands.hybrid_command(name='remove', description='Removes audio from the queue at a given index.')
    async def _remove(self, ctx: commands.Context, index: int):
        await self.ensure_voice_state(ctx)
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        server_name = ctx.guild.name
        server_id = ctx.guild.id
        user_hash = ctx.author.discriminator
        if len(ctx.voice_state.songs) == 0:
            print(f'{timestamp} - {ctx.author.display_name}#{user_hash} used the remove command in server "{server_name}" ({server_id})')
            return await ctx.send('Empty queue.')
        ctx.voice_state.songs.remove(index - 1)
        await ctx.voice_state.update_queue_message()
        await ctx.send('Successfully removed from the queue.')
        print(f'{timestamp} - {ctx.author.display_name}#{user_hash} used the remove command in server "{server_name}" ({server_id})')

    @commands.hybrid_command(name='play', description='Plays audio.')
    async def _play(self, ctx: commands.Context, *, search: str):
        await self.ensure_voice_state(ctx)
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        server_name = ctx.guild.name
        server_id = ctx.guild.id
        user_hash = ctx.author.discriminator
        destination = ctx.author.voice.channel

        if not ctx.voice_state.voice:
            ctx.voice_state.voice = await destination.connect()

        try:
            async with ctx.typing():
                print(f'{timestamp} - {ctx.author.display_name}#{user_hash} used the play command in server "{server_name}" ({server_id})')

                if 'spotify.com/playlist' in search:
                    await self.play_spotify_playlist(ctx, search)
                else:
                    search = search.replace(":", "")  # Remove colons from search
                    sources = await YTDLSource.create_source(ctx, search, loop=self.bot.loop)
                    print(f'Sources: {sources}')  # Debugging line to log sources

                    if sources is None or len(sources) == 0:
                        await ctx.send("No results found.")
                        return

                    if len(sources) > 1:
                        for source in sources:
                            song = Song(source)
                            await ctx.voice_state.songs.put(song)
                        added_message = f'{ctx.author.display_name} added a playlist to the queue.'
                    else:
                        song = Song(sources[0])
                        await ctx.voice_state.songs.put(song)
                        added_message = f'{ctx.author.display_name} added {song.source.title} by {song.source.uploader}.'

                    # Update the action message to be displayed in the Now Playing embed
                    ctx.voice_state.action_message = added_message

                    # Ensure that the Now Playing embed is updated properly
                    await ctx.voice_state.update_now_playing_embed()

                if not ctx.voice_state.is_playing:
                    await ctx.voice_state.audio_player_task()

                # Respond with "request sent" after processing
                await ctx.send("Request sent.")

        except YTDLError as e:
            await ctx.send('An error occurred while processing this request: {}'.format(str(e)))
        except Exception as e:
            await ctx.send(f'An unexpected error occurred: {e}')
            print(f'Error details: {e}')  # Debugging line to log the error details

        gc.collect()

    async def play_spotify_playlist(self, ctx, url):
        playlist_id = url.split('/')[-1].split('?')[0]
        playlist = sp.playlist(playlist_id)
        results = sp.playlist_tracks(playlist_id)

        # Introduce a flag before the playlist processing begins
        self.processing_playlist = True

        loading_message = await ctx.send(embed=discord.Embed(
            description=f"Adding songs from the Spotify playlist **{playlist['name']}**... :arrows_counterclockwise:",
            color=discord.Color.orange()
        ))

        batch_size = 10
        for start in range(0, len(results['items']), batch_size):
            if not ctx.voice_state.voice and self.processing_playlist:  # Check if the bot is still in the voice channel and if processing a playlist
                ctx.voice_state.songs.clear()
                await loading_message.edit(embed=discord.Embed(
                    description=f"Bot disconnected from the voice channel. Stopping playlist processing.",
                    color=discord.Color.red()
                ))
                self.processing_playlist = False  # Reset the flag
                return

            batch = results['items'][start:start + batch_size]
            for index, item in enumerate(batch):
                track = item['track']
                query = f"{track['name']} {track['artists'][0]['name']} Audio".replace(":", "")  # Remove colons from query and append "Audio"
                try:
                    source = await YTDLSource.create_source(ctx, query, loop=self.bot.loop)
                    if len(source) > 1:
                        for src in source:
                            song = Song(src)
                            await ctx.voice_state.songs.put(song)
                    else:
                        song = Song(source[0])
                        await ctx.voice_state.songs.put(song)
                    await ctx.voice_state.update_queue_message()  # Update queue message dynamically
                except YTDLError as e:
                    await ctx.send(f'An error occurred while processing track: {track["name"]} by {track["artists"][0]["name"]}: {str(e)}')
                embed = discord.Embed(
                    description=f"Adding songs from the Spotify playlist **{playlist['name']}**... ({start + index + 1}/{len(results['items'])}) :arrows_counterclockwise:",
                    color=discord.Color.orange()
                )
                await loading_message.edit(embed=embed)
            gc.collect()

        final_embed = discord.Embed(
            description=f"All songs from the Spotify playlist **{playlist['name']}** have been added.",
            color=discord.Color.green()
        )
        await loading_message.edit(embed=final_embed)

        # After processing the playlist, reset the flag
        self.processing_playlist = False

    
    # Ensure that the bot stops processing if disconnected
    async def check_voice_state(self, ctx: commands.Context):
        if not ctx.voice_state.voice:
            ctx.voice_state.songs.clear()
            ctx.voice_state.exists = False

async def setup(bot):
    await bot.add_cog(Music(bot))