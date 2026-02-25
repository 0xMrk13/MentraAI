import os
import logging
from pathlib import Path
from dotenv import load_dotenv

log = logging.getLogger("config")

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH, override=True)
BOT_API_KEY = os.getenv("BOT_API_KEY", "")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", "./data/studybot.sqlite3")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "qwen2.5:7b-instruct")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")

log.debug("BASE_DIR=%s", BASE_DIR)
log.debug("ENV_PATH=%s exists=%s", ENV_PATH, ENV_PATH.exists())
log.debug("TOKEN_LEN=%s", len(DISCORD_TOKEN or ""))
log.debug("DB_PATH=%s", DB_PATH)
log.debug("OPENAI_BASE_URL=%s", OPENAI_BASE_URL)
log.debug("DEFAULT_MODEL=%s", DEFAULT_MODEL)
log.debug("GUILD_ID=%s", GUILD_ID)


LLM_PROVIDER = os.getenv("LLM_PROVIDER", "local")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")