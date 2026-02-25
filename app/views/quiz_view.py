import asyncio
import logging
import time
from typing import Dict, List, Optional

import discord

from app.constants import AI_FOOTER
from app.models.quiz import QuizQuestion
from app.utils.discord_ui import pretty_bar
from app.views.components.quiz_buttons import AnswerButton, NextButton

log = logging.getLogger("MentraAI")

# -----------------------------
# Discord embed safe limits
# -----------------------------
FIELD_VALUE_MAX = 1024
OPTIONS_FIELD_SOFT_MAX = 950

# Final review caps
REVIEW_MAX_ITEMS = 5
REVIEW_EXPL_MAX = 120


def _ellipsize(s: str, max_len: int) -> str:
    s = (s or "").strip()
    if max_len <= 0:
        return ""
    if len(s) <= max_len:
        return s
    if max_len <= 1:
        return "…"
    return s[: max_len - 1].rstrip() + "…"


def _safe_two_lines(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return "-"
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join([" ".join(ln.split()) for ln in s.split("\n") if ln.strip()])
    return s


def _safe_explain(text: str, max_len: int = REVIEW_EXPL_MAX) -> str:
    s = (text or "").strip()
    s = " ".join(s.split())
    return _ellipsize(s, max_len)


def _normalize_topic(topic: str) -> str:
    clean_topic = (topic or "").strip()
    clean_topic = clean_topic.replace("@everyone", "everyone").replace("@here", "here")

    low = clean_topic.lower()
    prefixes = [
        "make me a quiz about",
        "make a quiz about",
        "quiz about",
        "a quiz about",
        "about",
    ]
    for p in prefixes:
        if low.startswith(p):
            clean_topic = clean_topic[len(p) :].strip()
            break

    clean_topic = " ".join(clean_topic.split())
    if not clean_topic:
        clean_topic = "general"

    if len(clean_topic) > 40:
        clean_topic = clean_topic[:40].rstrip() + "…"

    return clean_topic


class QuizView(discord.ui.View):
    """
    Flow:
    - Answer -> show Result + explanation
    - Next -> next question
    - Last question: Next becomes Finish, final summary is shown only when clicked
    """

    def __init__(
        self,
        *,
        store,
        owner_id: int,
        username: str,
        topic: str,
        questions: List[QuizQuestion],
        timed: bool = True,
        seconds_per_question: int = 60,
    ):
        super().__init__(timeout=1200)

        self.store = store
        self.owner_id = owner_id
        self.username = username
        self.topic = topic
        self.questions = questions

        self.timed = timed
        self.seconds_per_question = max(5, int(seconds_per_question))

        self.current = 0
        self.score = 0
        self.answered = False
        self.last_feedback = ""
        self.wrong_recap: List[Dict[str, str]] = []

        self._timer_task: Optional[asyncio.Task] = None
        self._message: Optional[discord.Message] = None
        self._deadline: float = 0.0

        self._lock = asyncio.Lock()
        self._last_click_ts = 0.0
        self._debounce_ms = 350
        self._busy = False

        # last-question flow state
        self._finished_ready = False

        # Buttons (layout requested: A B C D in one row, Next below)
        self.answer_buttons: List[AnswerButton] = []
        for i, label in enumerate(["A", "B", "C", "D"]):
            btn = AnswerButton(label=label, idx=i)
            btn.row = 0
            self.answer_buttons.append(btn)
            self.add_item(btn)

        self.next_button = NextButton()
        self.next_button.row = 0
        self.add_item(self.next_button)

        self._apply_choice_visibility()
        self._reset_answer_styles_neutral()

    # -----------------------------
    # helpers / guards
    # -----------------------------
    def _is_owner(self, interaction: discord.Interaction) -> bool:
        return getattr(interaction.user, "id", None) == self.owner_id

    def _debounced(self) -> bool:
        now = time.time()
        if (now - self._last_click_ts) * 1000 < self._debounce_ms:
            return True
        self._last_click_ts = now
        return False

    def _labels_for(self, n: int) -> List[str]:
        n = max(2, min(4, int(n)))
        return ["A", "B", "C", "D"][:n]

    def _current_labels(self) -> List[str]:
        q = self.questions[self.current]
        return self._labels_for(len(getattr(q, "choices", []) or []))

    def _clamp_correct_idx(self, correct_idx: int, labels: List[str]) -> int:
        if not labels:
            return 0
        if correct_idx < 0 or correct_idx >= len(labels):
            log.warning(
                "Invalid answer_index=%s for choices=%s (topic=%s q=%s)",
                correct_idx,
                len(labels),
                self.topic,
                self.current + 1,
            )
            return 0
        return correct_idx

    def _reset_answer_styles_neutral(self) -> None:
        """
        IMPORTANT: prevents green/red from sticking to next question.
        """
        for btn in self.answer_buttons:
            btn.style = discord.ButtonStyle.secondary

    async def _ack(self, interaction: discord.Interaction) -> None:
        if interaction.response.is_done():
            return
        try:
            await interaction.response.defer()
        except Exception:
            pass

    async def _edit(
        self, interaction: discord.Interaction, *, embed: discord.Embed
    ) -> None:
        if self._message:
            try:
                await self._message.edit(embed=embed, view=self)
                return
            except Exception:
                pass

        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception:
            try:
                await interaction.edit_original_response(embed=embed, view=self)
            except Exception:
                pass

    def _apply_choice_visibility(self) -> None:
        q = self.questions[self.current]
        n = len(getattr(q, "choices", []) or [])
        n = max(0, min(4, n))

        for i, btn in enumerate(self.answer_buttons):
            btn.disabled = self.answered or (i >= n)

        self.next_button.disabled = not self.answered

    # -----------------------------
    # attempt logging (NEW)
    # -----------------------------
    def _log_attempt(
        self,
        *,
        interaction: Optional[discord.Interaction],
        q: QuizQuestion,
        labels: List[str],
        picked_idx: Optional[int],
        correct_idx: int,
        clean_topic: str,
        picked_correct: bool,
        source: str = "discord",
    ) -> None:
        """
        Best-effort: save per-question attempt if store.add_quiz_attempt exists.
        Never raises.
        """
        fn = getattr(self.store, "add_quiz_attempt", None)
        if not callable(fn):
            return

        try:
            choices = list(getattr(q, "choices", []) or [])
            question_text = str(getattr(q, "question", "") or "").strip()
            explanation = str(getattr(q, "explanation", "") or "").strip() or None

            user_answer = None
            if picked_idx is not None and 0 <= picked_idx < len(labels):
                user_answer = labels[picked_idx]

            correct_answer = None
            if 0 <= correct_idx < len(labels):
                correct_answer = labels[correct_idx]

            guild_id = None
            if interaction is not None:
                guild_id = getattr(interaction, "guild_id", None)

            fn(
                user_id=int(self.owner_id),
                guild_id=int(guild_id) if guild_id is not None else None,
                topic=str(clean_topic),
                question=question_text,
                is_correct=bool(picked_correct),
                user_answer=user_answer,
                correct_answer=correct_answer,
                choices=[str(c) for c in choices] if choices else None,
                explanation=explanation,
                source=source,
            )
        except Exception:
            log.exception("Failed to write quiz_attempt to DB")

    # -----------------------------
    # timers
    # -----------------------------
    def attach_message(self, message: discord.Message) -> None:
        self._message = message

    def cancel_timer(self) -> None:
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
        self._timer_task = None

    def start_timer(self) -> None:
        self.cancel_timer()
        if not self.timed or not self._message:
            return
        self._deadline = time.time() + self.seconds_per_question
        self._timer_task = asyncio.create_task(self._timer_worker())

    def attempted_count(self) -> int:
        return self.current + (1 if self.answered else 0)

    def accuracy_pct(self) -> float:
        attempted = self.attempted_count()
        return 0.0 if attempted <= 0 else (self.score / attempted) * 100.0

    def seconds_left(self) -> int:
        if not self.timed or not self._deadline:
            return self.seconds_per_question
        return max(0, int(self._deadline - time.time()))

    # -----------------------------
    # embed
    # -----------------------------
    def build_embed(self) -> discord.Embed:
        q = self.questions[self.current]
        labels = self._current_labels()

        e = discord.Embed(title="🧪 Quiz")

        opt_lines: List[str] = []
        for i, c in enumerate((q.choices or [])[: len(labels)]):
            opt_lines.append(f"**{labels[i]}.**  {_safe_two_lines(str(c))}")

        opt_value = "\n".join(opt_lines) if opt_lines else "-"
        if len(opt_value) > OPTIONS_FIELD_SOFT_MAX:
            opt_value = _ellipsize(opt_value, OPTIONS_FIELD_SOFT_MAX)

        e.description = (
            f"**Topic:** {self.topic}\n\n"
            f"**Q{self.current + 1}/{len(self.questions)}**\n\n"
            f"**{_ellipsize(q.question, 800)}**\n\n"
            f"{opt_value}"
        )

        if self.last_feedback:
            e.add_field(
                name="Result", value=_ellipsize(self.last_feedback, 800), inline=False
            )

        attempted = self.attempted_count()
        acc = self.accuracy_pct()
        bar_w = min(12, max(6, len(self.questions)))
        bar = pretty_bar(self.current + 1, len(self.questions), width=bar_w)
        timer_part = f"⏳ {self.seconds_left()}s left" if self.timed else "⏱ no limit"

        e.set_footer(
            text=(
                f"Score {self.score}/{attempted} • Accuracy {acc:.0f}% • {timer_part}\n"
                f"{self.current + 1}/{len(self.questions)} {bar}\n"
                f"{AI_FOOTER}"
            )
        )
        return e

    def reset_for_next(self) -> None:
        self.answered = False
        self.last_feedback = ""
        self._finished_ready = False

        self._reset_answer_styles_neutral()

        self.next_button.disabled = True
        try:
            self.next_button.label = "Next ➜"
            self.next_button.style = discord.ButtonStyle.secondary
        except Exception:
            pass

        self._apply_choice_visibility()

    # -----------------------------
    # timer worker
    # -----------------------------
    async def _timer_worker(self) -> None:
        try:
            tick = 5
            while True:
                if self.answered or not self._message:
                    return
                left = self.seconds_left()
                if left <= 0:
                    break
                try:
                    self._apply_choice_visibility()
                    await self._message.edit(embed=self.build_embed(), view=self)
                except Exception:
                    pass
                await asyncio.sleep(min(tick, max(1, left)))
        except asyncio.CancelledError:
            return

        if self.answered or not self._message:
            return

        async with self._lock:
            if self.answered or not self._message:
                return

            q = self.questions[self.current]
            labels = self._current_labels()
            try:
                correct_idx = int(getattr(q, "answer_index", 0) or 0)
            except Exception:
                correct_idx = 0
            correct_idx = self._clamp_correct_idx(correct_idx, labels)

            # reveal correct (timeout = wrong)
            for i, btn in enumerate(self.answer_buttons):
                btn.disabled = True
                btn.style = (
                    discord.ButtonStyle.success
                    if i == correct_idx
                    else discord.ButtonStyle.secondary
                )

            self.answered = True
            self.next_button.disabled = False

            expl = _safe_explain(getattr(q, "explanation", "") or "", max_len=160)
            self.last_feedback = (
                f"⏱ **Time’s up!** Correct answer: **{labels[correct_idx]}**\n📝 {expl}"
            )

            # NEW: log attempt (timeout => is_correct False, user_answer None)
            clean_topic = _normalize_topic(self.topic)
            self._log_attempt(
                interaction=None,
                q=q,
                labels=labels,
                picked_idx=None,
                correct_idx=correct_idx,
                clean_topic=clean_topic,
                picked_correct=False,
                source="discord",
            )

            if self.current >= len(self.questions) - 1:
                self._finished_ready = True
                try:
                    self.next_button.label = "Finish ✅"
                    self.next_button.style = discord.ButtonStyle.success
                except Exception:
                    pass

            try:
                await self._message.edit(embed=self.build_embed(), view=self)
            except Exception:
                pass

    # -----------------------------
    # interactions
    # -----------------------------
    async def pick(self, interaction: discord.Interaction, idx: int) -> None:
        if not self._is_owner(interaction):
            await interaction.response.send_message(
                "❌ This quiz is not yours.", ephemeral=True
            )
            return

        await self._ack(interaction)

        if self._busy:
            return

        self._busy = True
        try:
            if self._debounced() or self.answered:
                return

            async with self._lock:
                if self.answered:
                    await self._edit(interaction, embed=self.build_embed())
                    return

                self.cancel_timer()

                q = self.questions[self.current]
                labels = self._current_labels()

                if idx < 0 or idx >= len(labels):
                    self._apply_choice_visibility()
                    await self._edit(interaction, embed=self.build_embed())
                    return

                try:
                    correct_idx = int(getattr(q, "answer_index", 0) or 0)
                except Exception:
                    correct_idx = 0
                correct_idx = self._clamp_correct_idx(correct_idx, labels)

                picked_correct = idx == correct_idx
                if picked_correct:
                    self.score += 1
                else:
                    self.wrong_recap.append(
                        {
                            "num": str(self.current + 1),
                            "your": labels[idx],
                            "correct": labels[correct_idx],
                            "explanation": str(getattr(q, "explanation", "") or ""),
                        }
                    )

                # lock answers, color result
                for i, btn in enumerate(self.answer_buttons):
                    btn.disabled = True
                    if i == correct_idx:
                        btn.style = discord.ButtonStyle.success
                    elif i == idx and not picked_correct:
                        btn.style = discord.ButtonStyle.danger
                    else:
                        btn.style = discord.ButtonStyle.secondary

                self.answered = True
                self.next_button.disabled = False

                expl_short = _safe_explain(
                    getattr(q, "explanation", "") or "", max_len=180
                )
                self.last_feedback = (
                    f"✅ **Correct**\n📝 {expl_short}"
                    if picked_correct
                    else f"❌ **Wrong** — Correct: **{labels[correct_idx]}**\n📝 {expl_short}"
                )

                # NEW: log attempt for this question
                clean_topic = _normalize_topic(self.topic)
                self._log_attempt(
                    interaction=interaction,
                    q=q,
                    labels=labels,
                    picked_idx=idx,
                    correct_idx=correct_idx,
                    clean_topic=clean_topic,
                    picked_correct=picked_correct,
                    source="discord",
                )

                if self.current >= len(self.questions) - 1:
                    self._finished_ready = True
                    try:
                        self.next_button.label = "Finish ✅"
                        self.next_button.style = discord.ButtonStyle.success
                    except Exception:
                        pass

                await self._edit(interaction, embed=self.build_embed())

        finally:
            self._busy = False

    async def go_next(self, interaction: discord.Interaction) -> None:
        if not self._is_owner(interaction):
            await interaction.response.send_message(
                "❌ This quiz is not yours.", ephemeral=True
            )
            return

        await self._ack(interaction)

        if self._busy:
            return

        self._busy = True
        try:
            if self._debounced():
                return

            async with self._lock:
                if not self.answered:
                    self._apply_choice_visibility()
                    await self._edit(interaction, embed=self.build_embed())
                    return

                if self.current >= len(self.questions) - 1 and self._finished_ready:
                    for item in self.children:
                        item.disabled = True

                    clean_topic = _normalize_topic(self.topic)

                    try:
                        guild_name = (
                            interaction.guild.name if interaction.guild else None
                        )

                        avatar_url = None
                        try:
                            avatar_url = interaction.user.display_avatar.url
                        except Exception:
                            avatar_url = None

                        display_name = (
                            getattr(interaction.user, "global_name", None)
                            or interaction.user.name
                        )

                        self.store.add_quiz_score(
                            guild_id=interaction.guild_id,
                            guild_name=guild_name,
                            user_id=self.owner_id,
                            username=self.username,
                            topic=clean_topic,
                            score=self.score,
                            total=len(self.questions),
                            duration_sec=60,
                            avatar_url=avatar_url,
                            display_name=display_name,
                        )
                    except Exception:
                        log.exception("Failed to write quiz score to DB")

                    total = len(self.questions)
                    acc = (self.score / total) * 100.0 if total else 0.0

                    end = discord.Embed(
                        title="🏁 Quiz finished",
                        description=(
                            f"🎯 Final Score: **{self.score}/{total}**\n"
                            f"📊 Accuracy: **{acc:.0f}%**"
                        ),
                    )

                    end.add_field(name="Topic", value=f"• {clean_topic}", inline=False)

                    # Review
                    if self.wrong_recap:
                        review_lines: List[str] = []
                        for w in self.wrong_recap[:REVIEW_MAX_ITEMS]:
                            expl = _safe_explain(
                                w.get("explanation", ""), max_len=REVIEW_EXPL_MAX
                            )
                            review_lines.append(
                                f"• Q{w['num']}: **{w['your']}** → **{w['correct']}** — {expl}"
                            )
                        if len(self.wrong_recap) > REVIEW_MAX_ITEMS:
                            review_lines.append(
                                f"• …and {len(self.wrong_recap) - REVIEW_MAX_ITEMS} more."
                            )

                        review_value = _ellipsize(
                            "\n".join(review_lines), FIELD_VALUE_MAX
                        )
                        end.add_field(
                            name="📝 Review (wrong answers)",
                            value=review_value,
                            inline=False,
                        )
                    else:
                        end.add_field(
                            name="✅ Review",
                            value="Perfect score. Nice work!",
                            inline=False,
                        )

                    end.set_footer(
                        text="Sorry if something felt off - I’m still learning too."
                    )
                    if self._message:
                        await self._message.edit(embed=end, view=None)
                    else:
                        await interaction.response.edit_message(embed=end, view=None)
                    return

                self.current += 1
                if self.current >= len(self.questions):
                    for item in self.children:
                        item.disabled = True
                    await self._edit(interaction, embed=self.build_embed())
                    return

                self.reset_for_next()
                await self._edit(interaction, embed=self.build_embed())
                self.start_timer()

        finally:
            self._busy = False
