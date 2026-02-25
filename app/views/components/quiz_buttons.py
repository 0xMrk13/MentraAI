import discord
from app.utils.discord_ui import internal_error

NEXT_LABEL = "Next ➜"
FINISH_LABEL = "Finish ✅"

class AnswerButton(discord.ui.Button):
    def __init__(self, label: str, idx: int):
        super().__init__(label=label, style=discord.ButtonStyle.secondary)  
        self.idx = idx

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not view or not hasattr(view, "pick"):
            return await internal_error(interaction)
        await view.pick(interaction, self.idx)

class NextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Next ➜",
            style=discord.ButtonStyle.secondary,  # grigio invece di blu
            disabled=True
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not view or not hasattr(view, "go_next"):
            return await internal_error(interaction)
        await view.go_next(interaction)
