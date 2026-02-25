from __future__ import annotations

import discord

LOADING_TEXT = {
    "ask": "🧠 Processing…",
    "quiz": "🧪 Assembling the quiz…",
    "flashcards": "🗃️ Generating flashcards…",
    "plan": "📘 Building your study plan…",
    "resources": "📚 Fetching resources…",
    "default": "⚙️ Working…",
}


async def start_loading(interaction: discord.Interaction, kind: str = "default") -> discord.Message | None:
    text = LOADING_TEXT.get(kind, LOADING_TEXT["default"])
    try:
        return await interaction.followup.send(text, ephemeral=True)
    except Exception:
        return None




async def stop_loading(msg: discord.Message | None) -> None:
    if not msg:
        return
    try:
        await msg.delete()
    except Exception:
        pass
