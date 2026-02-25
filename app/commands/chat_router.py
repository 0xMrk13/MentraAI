from __future__ import annotations

import re
import time
import discord

from app.commands.chat_ai_router import infer_intent
from app.commands.quiz_commands import run_quiz_from_chat
from app.commands.study import run_ask_from_chat, run_plan_from_chat
from app.services.llm import LLMClient
from app.commands.flashcards_commands import run_flashcards_from_chat

MENTRA_PREFIX = "mentra"
COOLDOWN_S = 2.5

BLOCKED_CHAT = {
    "wipe",
    "wipe_admin",
    "wipeadmin",
    "usersetkey",
    "userdelkey",
    "setkey",
    "delkey",
}

_last_chat: dict[int, float] = {}


def _strip_bot_mention(bot_user: discord.ClientUser | None, content: str) -> str | None:
    if not bot_user:
        return None
    if content.startswith(f"<@{bot_user.id}>") or content.startswith(
        f"<@!{bot_user.id}>"
    ):
        return re.sub(r"^<@!?\d+>\s*", "", content).strip()
    return None


def _parse_days(text: str) -> tuple[str, int | None]:
    t = (text or "").strip()
    m = re.search(r"(?i)\b(\d{1,2})\s*days?\b", t)
    if not m:
        return t, None
    days = int(m.group(1))
    t2 = (t[: m.start()] + t[m.end() :]).strip()
    t2 = re.sub(r"\s{2,}", " ", t2).strip()
    return t2, days


def _auto_correct_intent(text: str) -> tuple[str, str] | None:
    t = text.lower()

    quiz_words = ["quiz", "question", "questions", "test"]
    flash_words = ["flashcard", "flashcards", "cards"]
    plan_words = ["plan", "roadmap", "schedule", "study plan"]
    ask_words = ["what", "how", "why", "explain", "help", "understand"]

    if any(w in t for w in quiz_words):
        return ("quiz", text)

    if any(w in t for w in flash_words):
        return ("flashcards", text)

    if any(w in t for w in plan_words):
        return ("plan", text)

    if any(w in t for w in ask_words):
        return ("ask", text)

    return None


def register_chat_router(client: discord.Client, store, llm: LLMClient):
    @client.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return

        raw = (message.content or "").strip()
        if not raw:
            return

        text: str | None = None
        if raw.lower().startswith(MENTRA_PREFIX + " "):
            text = raw[len(MENTRA_PREFIX) :].strip()

        if text is None:
            text = _strip_bot_mention(client.user, raw)

        if text is None:
            return

        now = time.time()
        last = _last_chat.get(message.author.id, 0.0)
        if now - last < COOLDOWN_S:
            return
        _last_chat[message.author.id] = now

        lowered_compact = text.lower().replace("/", "").replace(" ", "")
        if lowered_compact in BLOCKED_CHAT:
            await message.reply(
                "For safety, please use the slash command for that action."
            )
            return

        lower = text.lower().strip()

        if lower.startswith("quiz "):
            topic = text[5:].strip()
            if not topic:
                await message.reply("Usage: `mentra quiz <topic>`")
                return
            await run_quiz_from_chat(
                client=client,
                channel=message.channel,
                user=message.author,
                guild_id=message.guild.id if message.guild else 0,
                topic=topic,
                num_questions=5,
                store=store,
                llm=llm,
            )
            return

        if lower.startswith("ask "):
            question = text[4:].strip()
            if not question:
                await message.reply("Usage: `mentra ask <your question>`")
                return
            await run_ask_from_chat(
                message.channel,
                message.author,
                store,
                llm,
                question,
            )
            return

        if lower.startswith("plan "):
            rest = text[5:].strip()
            if not rest:
                await message.reply("Usage: `mentra plan <topic>`")
                return
            topic, days = _parse_days(rest)
            if not topic:
                topic = "general cybersecurity"
            if days is None:
                days = 7
            await run_plan_from_chat(
                message.channel,
                message.author,
                store,
                llm,
                topic,
                days=days,
            )
            return

        if lower.startswith("flashcards "):
            topic = text[11:].strip()
            if not topic:
                await message.reply("Usage: `mentra flashcards <topic>`")
                return
            await run_flashcards_from_chat(
                channel=message.channel,
                user=message.author,
                topic=topic,
                store=store,
                llm=llm,
            )
            return

        auto = _auto_correct_intent(text)
        if auto:
            intent, value = auto

            if intent == "quiz":
                await run_quiz_from_chat(
                    client=client,
                    channel=message.channel,
                    user=message.author,
                    guild_id=message.guild.id if message.guild else 0,
                    topic=value,
                    num_questions=5,
                    store=store,
                    llm=llm,
                )
                return

            if intent == "flashcards":
                await run_flashcards_from_chat(
                    channel=message.channel,
                    user=message.author,
                    topic=value,
                    store=store,
                    llm=llm,
                )
                return

            if intent == "plan":
                topic, days = _parse_days(value)
                if not topic:
                    topic = "general cybersecurity"
                if days is None:
                    days = 7
                await run_plan_from_chat(
                    message.channel,
                    message.author,
                    store,
                    llm,
                    topic,
                    days=days,
                )
                return

            if intent == "ask":
                await run_ask_from_chat(
                    message.channel,
                    message.author,
                    store,
                    llm,
                    value,
                )
                return

        data = await infer_intent(llm, text)
        intent = data.get("intent", "unknown")

        if intent == "quiz":
            topic = data.get("topic") or text
            await run_quiz_from_chat(
                client=client,
                channel=message.channel,
                user=message.author,
                guild_id=message.guild.id if message.guild else 0,
                topic=topic,
                num_questions=5,
                store=store,
                llm=llm,
            )
            return

        if intent == "ask":
            question = data.get("question") or text
            await run_ask_from_chat(
                message.channel,
                message.author,
                store,
                llm,
                question,
            )
            return

        if intent == "flashcards":
            topic = data.get("topic") or text
            await run_flashcards_from_chat(
                channel=message.channel,
                user=message.author,
                topic=topic,
                store=store,
                llm=llm,
            )
            return

        if intent == "plan":
            plan_req = data.get("plan_request") or data.get("topic") or text
            topic, days = _parse_days(plan_req)
            if not topic:
                topic = "general cybersecurity"
            if days is None:
                days = 7
            await run_plan_from_chat(
                message.channel,
                message.author,
                store,
                llm,
                topic,
                days=days,
            )
            return

        await message.reply(
            "I didn’t understand that.\n"
            "Examples:\n"
            "- `mentra quiz windows privilege escalation`\n"
            "- `mentra ask what is SSRF?`\n"
            "- `mentra plan active directory 7days`\n"
            "- `mentra flashcards web security`\n"
        )
