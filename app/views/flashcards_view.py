import random
import time
from typing import List, Optional

import discord

from app.models.cards import Flashcard
from app.utils.discord_ui import pretty_bar, elapsed_s
from app.views.components.flashcards_buttons import (
    BackCardButton,
    RevealButton,
    NextCardButton,
    ShuffleButton,
)


def _format_answer_block(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return "-"
    text = " ".join(text.split())
    return text[:900].strip()


def flashcard_embed(
    *,
    topic: str,
    idx: int,
    total: int,
    q: str,
    a: str,
    revealed: bool,
    revealed_count: int,
    started_at_ts: float,
) -> discord.Embed:
    prog = pretty_bar(idx + 1, total, max_width=10)
    elapsed = elapsed_s(started_at_ts)

    question = (q or "-")[:900].strip()
    answer = _format_answer_block(a) if revealed else "||Click **Reveal Answer** to show it.||"

    desc = (
        f"**Topic:** {topic}\n\n"
        f"**Card {idx + 1}/{total}**\n"
        f"**Question**\n{question}\n\n"
        f"**Answer**\n{answer}"
    )

    e = discord.Embed(title="🧠 Flashcards", description=desc)
    e.set_footer(
        text=f"{idx+1}/{total} {prog} • Revealed {revealed_count}/{total} • {elapsed}s\n"
        f"Sorry if something felt off — I’m still learning too."
    )
    return e


class FlashcardsView(discord.ui.View):
    def __init__(self, owner_id: int, topic: str, cards: List[Flashcard]):
        super().__init__(timeout=900)

        self.owner_id = owner_id
        self.topic = topic
        self.cards = cards

        self.i = 0
        self.revealed_set: set[int] = set()  # per-card revealed

        self.started_at_ts = time.time()
        self._message: Optional[discord.Message] = None

        self.btn_back = BackCardButton()
        self.btn_reveal = RevealButton()
        self.btn_next = NextCardButton()
        self.btn_shuffle = ShuffleButton()

        self.add_item(self.btn_back)
        self.add_item(self.btn_reveal)
        self.add_item(self.btn_next)
        self.add_item(self.btn_shuffle)

        self._refresh_buttons()

    def attach_message(self, msg: discord.Message) -> None:
        self._message = msg

    def _owner_only(self, interaction: discord.Interaction) -> bool:
        return getattr(interaction.user, "id", None) == self.owner_id

    def _is_revealed(self) -> bool:
        return self.i in self.revealed_set

    def _revealed_count(self) -> int:
        return len(self.revealed_set)

    def _refresh_buttons(self) -> None:
        revealed = self._is_revealed()
        self.btn_back.disabled = (self.i == 0)
        self.btn_reveal.disabled = revealed
        self.btn_next.disabled = (not revealed)

    def current_embed(self) -> discord.Embed:
        c = self.cards[self.i]
        return flashcard_embed(
            topic=self.topic,
            idx=self.i,
            total=len(self.cards),
            q=c.q,
            a=c.a,
            revealed=self._is_revealed(),
            revealed_count=self._revealed_count(),
            started_at_ts=self.started_at_ts,
        )

    async def reveal(self, interaction: discord.Interaction):
        if not self._owner_only(interaction):
            await interaction.response.send_message("❌ These flashcards are not yours.", ephemeral=True)
            return

        if self._is_revealed():
            await interaction.response.edit_message(embed=self.current_embed(), view=self)
            return

        self.revealed_set.add(self.i)
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.current_embed(), view=self)

    async def next(self, interaction: discord.Interaction):
        if not self._owner_only(interaction):
            await interaction.response.send_message("❌ These flashcards are not yours.", ephemeral=True)
            return

        if not self._is_revealed():
            await interaction.response.send_message("🔒 Reveal the answer first.", ephemeral=True)
            return

        self.i += 1
        self._refresh_buttons()

        if self.i >= len(self.cards):
            total = len(self.cards)
            elapsed = max(1, int(time.time() - self.started_at_ts))
            rc = self._revealed_count()
            revealed_pct = int(round((rc / total) * 100)) if total else 0
            badge = "🏆" if revealed_pct >= 90 else ("🎯" if revealed_pct >= 70 else "📘")
            bar = pretty_bar(rc, total, max_width=10)

            summary = discord.Embed(
                title="🏁 Flashcards finished",
                description=(
                    f"**Topic:** {self.topic}\n\n"
                    f"**Revealed:** **{revealed_pct}%**\n"
                    f"**Progress:** {bar}  {rc}/{total}\n"
                    f"**Time:** {elapsed}s"
                ),
            )
            summary.add_field(
                name="Next move",
                value="Run **/flashcards** again or switch to **/quiz** to validate knowledge.",
                inline=False,
            )
            summary.set_footer(text="Sorry if something felt off — I’m still learning too.")

            # hide buttons at the end
            if self._message:
                await self._message.edit(embed=summary, view=None)
            else:
                await interaction.response.edit_message(embed=summary, view=None)
            return

        await interaction.response.edit_message(embed=self.current_embed(), view=self)

    async def back(self, interaction: discord.Interaction):
        if not self._owner_only(interaction):
            await interaction.response.send_message("❌ These flashcards are not yours.", ephemeral=True)
            return

        if self.i <= 0:
            await interaction.response.edit_message(embed=self.current_embed(), view=self)
            return

        self.i -= 1
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.current_embed(), view=self)

    async def shuffle(self, interaction: discord.Interaction):
        if not self._owner_only(interaction):
            await interaction.response.send_message("❌ These flashcards are not yours.", ephemeral=True)
            return

        random.shuffle(self.cards)
        self.i = 0
        self.revealed_set.clear()
        self.started_at_ts = time.time()

        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.current_embed(), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self._message:
            try:
                await self._message.edit(view=self)
            except Exception:
                pass
