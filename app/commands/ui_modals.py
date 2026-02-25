import discord
from app.utils.embeds import make_embed


class ApiKeyModal(discord.ui.Modal, title="Set your LLM API key (optional)"):
    api_key = discord.ui.TextInput(
        label="API Key (leave empty for local Ollama)",
        style=discord.TextStyle.short,
        placeholder="sk-... (optional)",
        required=False,
        min_length=0,
        max_length=200,
    )

    def __init__(self, store):
        super().__init__()
        self.store = store

    async def on_submit(self, interaction: discord.Interaction):
        key = str(self.api_key.value).strip()
        self.store.set_key(interaction.user.id, key)

        e = make_embed(
            title="✅ API Key Saved",
            description="You can now use **/ask**, **/quiz**, **/plan**, **/flashcards**.",
            fields=[{"name": "Mode", "value": ("Cloud key saved" if key else "Local Ollama (no key)"), "inline": False}],
            footer="Tip: use /delkey to remove it anytime.",
        )
        await interaction.response.send_message(embed=e, ephemeral=True)
