import random
import logging
import discord
from discord.ext import tasks

log = logging.getLogger(__name__)

DEFAULT_STATUSES = [
    "🧠 Training hackers",
    "📚 Reinforcing concepts",
    "🧭 Guiding recon",
    "🔎 Mentraing enumeration",
    "📡 Scanning labs",
    "🧪 Exploit practice",
    "🔐 Cracking hashes",
    "🧗 PrivEsc coaching",
    "📁 Looting knowledge",
    "🛠️ Payload crafting",
    "🌐 Web attack drills",
    "🧠 Buffer overflow lab",
    "📜 Study session active",
    "🏴‍☠️ Capturing flags",
    "🎓 OSCP mindset",
]


def create_status_tasks(client: discord.Client):
    @tasks.loop(minutes=20)
    async def rotate_status():
        try:
            await client.change_presence(
                status=discord.Status.online,
                activity=discord.Game(name=random.choice(DEFAULT_STATUSES)),
            )
        except Exception:
            log.exception("Failed to rotate status")

    @rotate_status.before_loop
    async def before_rotate_status():
        await client.wait_until_ready()

    return rotate_status
