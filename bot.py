import io
import sys
import logging
import random

import discord
from discord import app_commands

from app.commands.chat_router import register_chat_router
from app.commands import (
    register_admin_commands,
    register_flashcards_commands,
    register_quiz_commands,
    register_stats_commands,
    register_study_commands,
)
from app.constants import BOT_MODE, BOT_VERSION
from app.utils.logger_setup import setup_logging
from app.utils.startup_banner import startup_banner
from app.services.status_rotation import create_status_tasks, DEFAULT_STATUSES

from config import DISCORD_TOKEN, DB_PATH, OPENAI_BASE_URL, DEFAULT_MODEL, GUILD_ID, GROQ_BASE_URL, GROQ_MODEL,  LLM_PROVIDER
from app.db import KeyStore
from app.services.llm import LLMClient


class _FilterPyNaCl(io.TextIOWrapper):
    def write(self, text):
        if "PyNaCl is not installed" in text:
            return 0
        return super().write(text)


def build_client():
    intents = discord.Intents.default()
    intents.message_content = True

    store = KeyStore(DB_PATH)
    if LLM_PROVIDER == "groq":
        llm = LLMClient(
            base_url=GROQ_BASE_URL,
            default_model=GROQ_MODEL,
            openai_base_url=GROQ_BASE_URL,         
            openai_default_model=GROQ_MODEL,
            prefer_responses_api=False,             
            force_chat_completions=True,            
        )
    else:
        llm = LLMClient(
            base_url=OPENAI_BASE_URL,
            default_model=DEFAULT_MODEL,
            openai_base_url="https://api.openai.com/v1",
            openai_default_model="gpt-4.1",
        )

    class StudyBot(discord.Client):
        def __init__(self) -> None:
            super().__init__(intents=intents)
            self.tree = app_commands.CommandTree(self)

        async def setup_hook(self) -> None:
            register_admin_commands(self, store, llm)
            register_study_commands(self, store, llm)
            register_quiz_commands(self, store, llm)
            register_flashcards_commands(self, store, llm)
            register_stats_commands(self, store, llm)

            if GUILD_ID:
                guild = discord.Object(id=GUILD_ID)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            else:
                await self.tree.sync()

    client = StudyBot()
    register_chat_router(client, store, llm)

    rotate_status = create_status_tasks(client)

    @client.event
    async def on_ready() -> None:
        if getattr(client, "_ready_once", False):
            return
        client._ready_once = True

        provider = (
            "Ollama (OpenAI-compatible)" if "11434" in OPENAI_BASE_URL else "OpenAI"
        )
        cmd_count = len(client.tree.get_commands())

        startup_banner(
            provider=provider,
            model=DEFAULT_MODEL,
            api=OPENAI_BASE_URL.replace("http://", "").replace("https://", ""),
            commands=cmd_count,
            version=BOT_VERSION,
            mode=BOT_MODE,
        )

        # status iniziale (uno a caso dalla lista statica)
        await client.change_presence(
            status=discord.Status.online,
            activity=discord.Game(name=random.choice(DEFAULT_STATUSES)),
        )

        if not rotate_status.is_running():
            rotate_status.start()

    return client


def main() -> None:
    from app.utils.single_instance import acquire_lock

    acquire_lock()

    sys.stderr = _FilterPyNaCl(sys.stderr.buffer, encoding="utf-8")

    setup_logging(console_level="INFO", file_level="DEBUG")
    logging.getLogger(__name__)

    if not DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN missing in .env")

    client = build_client()
    client.run(DISCORD_TOKEN)


if __name__ == "__main__":
    import multiprocessing as mp

    mp.freeze_support()
    main()
