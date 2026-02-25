import discord
from typing import Optional, Callable

from app.constants import QUIZ_TOPICS
from app.utils.discord_ui import silent_ack


class CustomTopicModal(discord.ui.Modal, title="Custom topic"):
    topic = discord.ui.TextInput(
        label="Topic",
        placeholder="e.g. phishing, SSRF, JWT, Windows persistence...",
        required=True,
        max_length=80,
    )

    def __init__(self, on_submit_cb: Callable[[str], None]):
        super().__init__()
        self._on_submit_cb = on_submit_cb

    async def on_submit(self, interaction: discord.Interaction):
        self._on_submit_cb(str(self.topic.value).strip())
        await interaction.response.defer()  


class TopicPickerView(discord.ui.View):
    def __init__(self, owner_id: int, *, placeholder: str = "Pick a topic…"):
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.selected_topic: Optional[str] = None

        options = [discord.SelectOption(label=t, value=t) for t in QUIZ_TOPICS[:25]]

        self.select = discord.ui.Select(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
        )
        self.select.callback = self._on_select  
        self.add_item(self.select)

    def _owner_only(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    async def _on_select(self, interaction: discord.Interaction):
        if not self._owner_only(interaction):
            return await interaction.response.send_message("❌ Not your menu.", ephemeral=True)

        self.selected_topic = self.select.values[0]
        self.stop()
        await silent_ack(interaction)


    @discord.ui.button(label="Custom topic…", style=discord.ButtonStyle.secondary)
    async def custom(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._owner_only(interaction):
            return await interaction.response.send_message("❌ Not your menu.", ephemeral=True)

        def _set_topic(t: str):
            self.selected_topic = t
            self.stop()

        await interaction.response.send_modal(CustomTopicModal(_set_topic))

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._owner_only(interaction):
            return await interaction.response.send_message("❌ Not your menu.", ephemeral=True)
        self.selected_topic = None
        self.stop()
        await interaction.response.defer()
