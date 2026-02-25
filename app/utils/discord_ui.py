import time
from typing import Optional, Type, TypeVar

import discord

T = TypeVar("T")

import math

def pretty_bar(current_1based: int, total: int, width: int = 12, max_width: int = 12) -> str:

    if total <= 0:
        return ""

    w = width if width is not None else max_width
    w = min(w, max_width)

    w = max(3, min(int(w), 16))

    current = max(0, min(int(current_1based), int(total)))
    ratio = current / total if total else 0.0
    filled = int(round(ratio * w))
    filled = max(0, min(filled, w))

    return f"[{'#' * filled + '-' * (w - filled)}]"



def elapsed_s(started_at_ts: float) -> int:
    return max(0, int(time.time() - started_at_ts))

async def silent_ack(interaction: discord.Interaction) -> None:
    try:
        if not interaction.response.is_done():
            await interaction.response.defer()
    except Exception:
        pass

async def internal_error(interaction: discord.Interaction) -> None:
    if not interaction.response.is_done():
        await interaction.response.send_message("❌ Internal error.", ephemeral=True)

async def get_view(interaction: discord.Interaction, view_obj, view_type: Type[T]) -> Optional[T]:
    if isinstance(view_obj, view_type):
        return view_obj
    await internal_error(interaction)
    return None
