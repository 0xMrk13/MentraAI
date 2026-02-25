import discord
from app.utils.discord_ui import internal_error

class BackCardButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Back ⬅", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not view or not hasattr(view, "back"):
            return await internal_error(interaction)
        await view.back(interaction)

class RevealButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Reveal Answer", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not view or not hasattr(view, "reveal"):
            return await internal_error(interaction)
        await view.reveal(interaction)


class NextCardButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Next ➜", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not view or not hasattr(view, "next"):
            return await internal_error(interaction)
        await view.next(interaction)


class ShuffleButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Shuffle 🔀", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not view or not hasattr(view, "shuffle"):
            return await internal_error(interaction)
        await view.shuffle(interaction)
