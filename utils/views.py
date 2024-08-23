import discord
import gc
from discord.ext import commands

class QueuePages(discord.ui.View):
    def __init__(self, ctx: commands.Context, pages: list, current_page: int = 0):
        super().__init__(timeout=None)  # Set timeout to None
        self.ctx = ctx
        self.pages = pages
        self.current_page = current_page

        self.previous_button = discord.ui.Button(label='Previous', style=discord.ButtonStyle.primary, custom_id='previous')
        self.next_button = discord.ui.Button(label='Next', style=discord.ButtonStyle.primary, custom_id='next')
        self.previous_button.callback = self.previous_page
        self.next_button.callback = self.next_page

        self.add_item(self.previous_button)
        self.add_item(self.next_button)
        self.update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.ctx.author

    def update_buttons(self):
        self.previous_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= len(self.pages) - 1

    async def previous_page(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    async def next_page(self, interaction: discord.Interaction):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

class NowPlayingButtons(discord.ui.View):
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=None)
        self.ctx = ctx

        buttons = [
            ("Pause", self.pause_callback, "⏸️"),
            ("Resume", self.resume_callback, "▶️"),
            ("Shuffle", self.shuffle_callback, "🔀"),
            ("Queue", self.queue_callback, "📜"),
            ("Skip", self.skip_callback, "⏭️"),
            ("Clear", self.clear_callback, "🧹"),
            ("Volume Up", self.volume_up_callback, "🔊"),
            ("Volume Down", self.volume_down_callback, "🔉")
        ]

        for label, callback, emoji in buttons:
            button = discord.ui.Button(label=label, style=discord.ButtonStyle.primary, emoji=emoji)
            button.callback = callback
            self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.ctx.author

    async def pause_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        ctx = self.ctx
        player = ctx.voice_client
        if player and player.is_playing():
            player.pause()
            ctx.voice_state.action_message = f"**{interaction.user.display_name} paused the player.**"
            await ctx.voice_state.update_now_playing_embed(interaction)

    async def resume_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        ctx = self.ctx
        player = ctx.voice_client
        if player and player.is_paused():
            player.resume()
            ctx.voice_state.action_message = f"**{interaction.user.display_name} resumed the player.**"
            await ctx.voice_state.update_now_playing_embed(interaction)

    async def shuffle_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        ctx = self.ctx
        if ctx.voice_state and ctx.voice_state.is_playing:
            ctx.voice_state.songs.shuffle()
            await ctx.voice_state.update_queue_message()
            ctx.voice_state.action_message = f"**{interaction.user.display_name} shuffled the queue.**"
            await ctx.voice_state.update_now_playing_embed(interaction)
            gc.collect()

    async def queue_callback(self, interaction: discord.Interaction):
        ctx = self.ctx
        if ctx.voice_state and ctx.voice_state.is_playing:
            await ctx.invoke(ctx.bot.get_command('queue'))
        await interaction.response.defer()
        await interaction.edit_original_message(view=NowPlayingButtons(ctx))

    async def skip_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        ctx = self.ctx
        if ctx.voice_state and ctx.voice_state.is_playing:
            ctx.voice_state.action_message = f"**{interaction.user.display_name} skipped the song.**"
            await ctx.voice_state.update_now_playing_embed(interaction)
            ctx.voice_state.skip()

    async def clear_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        ctx = self.ctx
        if ctx.voice_state and ctx.voice_state.is_playing:
            confirmation_message = await ctx.send("Are you sure you want to clear the queue?", view=ClearQueueConfirmation(ctx, ctx.voice_state))
        await interaction.response.defer()
        await interaction.edit_original_message(view=NowPlayingButtons(ctx))

    async def volume_up_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        ctx = self.ctx
        if ctx.voice_state:
            await ctx.voice_state.change_volume(10, interaction)  # Increase volume by 10%
        await interaction.response.defer()

    async def volume_down_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        ctx = self.ctx
        if ctx.voice_state:
            await ctx.voice_state.change_volume(-10, interaction)  # Decrease volume by 10%
        await interaction.response.defer()
        
class ClearQueueConfirmation(discord.ui.View):
    def __init__(self, ctx: commands.Context, voice_state):
        super().__init__(timeout=None)  # Set timeout to None
        self.ctx = ctx
        self.voice_state = voice_state

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.ctx.author

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.voice_state.songs.clear()
        await self.voice_state.update_queue_message()
        await interaction.response.edit_message(content="The queue has been cleared.", view=None)
        gc.collect()

    @discord.ui.button(label="No", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelled clearing the queue.", view=None)